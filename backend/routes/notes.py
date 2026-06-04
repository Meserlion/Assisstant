import json
import uuid
import tempfile
import os
from datetime import datetime, timezone

import aiofiles
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import StreamingResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from config import settings
from database import get_db
from services import whisper_service, claude_service, chroma_service

router = APIRouter(prefix="/notes", tags=["notes"])
api_key_header = APIKeyHeader(name="X-API-Key")


def verify_key(key: str = Depends(api_key_header)):
    if key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


class NoteResponse(BaseModel):
    id: str
    created_at: str
    raw_text: str
    tags: list[str]
    summary: str


class NoteUpdateRequest(BaseModel):
    text: str
    client_timezone: str = None
    client_local_time: str = None


class QueryRequest(BaseModel):
    text: str
    history: list[dict] = []


class QueryResponse(BaseModel):
    query: str
    answer: str
    sources: list[NoteResponse]


def _save_note_from_text(text: str, client_timezone: str = None, client_local_time: str = None) -> NoteResponse:
    """Shared helper: analyse text, persist to SQLite + Chroma, auto-create reminder if needed."""
    analysis = claude_service.tag_note(text, client_timezone, client_local_time)
    tags = analysis["tags"]
    summary = analysis["summary"]
    note_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    db = get_db()
    db.execute(
        "INSERT INTO notes (id, created_at, raw_text, tags, summary) VALUES (?, ?, ?, ?, ?)",
        (note_id, created_at, text, json.dumps(tags), summary),
    )
    db.commit()
    db.close()

    chroma_service.add_note(note_id, text, {"created_at": created_at, "tags": json.dumps(tags), "summary": summary})

    if analysis["is_reminder"] and analysis["reminder_details"]:
        rem_details = analysis["reminder_details"]
        title = rem_details.get("title") or text[:80]
        remind_at = rem_details.get("remind_at")
        if remind_at:
            reminder_id = str(uuid.uuid4())
            db = get_db()
            db.execute(
                "INSERT INTO reminders (id, title, remind_at, created_at) VALUES (?, ?, ?, ?)",
                (reminder_id, title, remind_at, created_at),
            )
            db.commit()
            db.close()
            from services import google_calendar
            from datetime import timedelta
            if google_calendar.is_connected():
                try:
                    remind_at_dt = datetime.fromisoformat(remind_at.replace("Z", "+00:00"))
                    end_iso = (remind_at_dt + timedelta(hours=1)).isoformat()
                    event_id = google_calendar.create_event(title, remind_at, end_iso)
                    db = get_db()
                    db.execute("UPDATE reminders SET google_event_id = ? WHERE id = ?", (event_id, reminder_id))
                    db.commit()
                    db.close()
                except Exception as e:
                    print(f"Failed to sync auto-reminder to Google Calendar: {e}")

    return NoteResponse(id=note_id, created_at=created_at, raw_text=text, tags=tags, summary=summary)


@router.post("/capture", response_model=NoteResponse, dependencies=[Depends(verify_key)])
async def capture_note(
    audio: UploadFile = File(...),
    client_timezone: str = Form(None),
    client_local_time: str = Form(None)
):
    suffix = os.path.splitext(audio.filename or "audio.webm")[1] or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        async with aiofiles.open(tmp.name, "wb") as f:
            await f.write(await audio.read())
        tmp_path = tmp.name
    try:
        text = whisper_service.transcribe(tmp_path)
    finally:
        os.unlink(tmp_path)
    return _save_note_from_text(text, client_timezone, client_local_time)


class TextNoteRequest(BaseModel):
    text: str
    client_timezone: str = None
    client_local_time: str = None


@router.post("/text", response_model=NoteResponse, dependencies=[Depends(verify_key)])
def create_text_note(req: TextNoteRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Note text cannot be empty")
    return _save_note_from_text(req.text.strip(), req.client_timezone, req.client_local_time)


@router.get("/", response_model=list[NoteResponse], dependencies=[Depends(verify_key)])
def list_notes(limit: int = 50, offset: int = 0):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM notes WHERE tags NOT LIKE '%\"calendar\"%' ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)
    ).fetchall()
    db.close()
    return [
        NoteResponse(
            id=r["id"],
            created_at=r["created_at"],
            raw_text=r["raw_text"],
            tags=json.loads(r["tags"]),
            summary=r["summary"],
        )
        for r in rows
    ]


@router.delete("/{note_id}", dependencies=[Depends(verify_key)])
def delete_note(note_id: str):
    db = get_db()
    result = db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    db.commit()
    db.close()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Note not found")
    chroma_service.delete_note(note_id)
    return {"deleted": note_id}


@router.put("/{note_id}", response_model=NoteResponse, dependencies=[Depends(verify_key)])
def update_note(note_id: str, req: NoteUpdateRequest):
    db = get_db()
    row = db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    if not row:
        db.close()
        raise HTTPException(status_code=404, detail="Note not found")

    # Regenerate tags & summary using the new text
    analysis = claude_service.tag_note(req.text, req.client_timezone, req.client_local_time)
    tags = analysis["tags"]
    summary = analysis["summary"]

    db.execute(
        "UPDATE notes SET raw_text = ?, tags = ?, summary = ? WHERE id = ?",
        (req.text, json.dumps(tags), summary, note_id)
    )
    db.commit()
    db.close()

    # Update Vector Store (Chroma)
    chroma_service.delete_note(note_id)
    chroma_service.add_note(note_id, req.text, {"created_at": row["created_at"], "tags": json.dumps(tags), "summary": summary})

    return NoteResponse(id=note_id, created_at=row["created_at"], raw_text=req.text, tags=tags, summary=summary)


class RewriteRequest(BaseModel):
    text: str
    instruction: str


@router.post("/rewrite", dependencies=[Depends(verify_key)])
def rewrite_note(req: RewriteRequest):
    if not req.text.strip() or not req.instruction.strip():
        raise HTTPException(status_code=400, detail="text and instruction are required")
    rewritten = claude_service.rewrite_note(req.text.strip(), req.instruction.strip())
    return {"rewritten": rewritten}


@router.post("/transcribe", dependencies=[Depends(verify_key)])
async def transcribe_audio(audio: UploadFile = File(...)):
    suffix = os.path.splitext(audio.filename or "audio.webm")[1] or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        async with aiofiles.open(tmp.name, "wb") as f:
            await f.write(await audio.read())
        tmp_path = tmp.name

    try:
        text = whisper_service.transcribe(tmp_path)
    finally:
        os.unlink(tmp_path)

    return {"text": text}


@router.post("/query", response_model=QueryResponse, dependencies=[Depends(verify_key)])
def query_notes(req: QueryRequest):
    # Rewrite the search query for vector retrieval using history if present
    search_query = claude_service.rewrite_query(req.text, req.history)
    matches = chroma_service.search_notes(search_query)

    # 1. Fetch upcoming schedule context (next 7 days) from local notes DB (synced calendar events)
    from datetime import datetime, timezone, timedelta
    now_utc = datetime.now(timezone.utc)
    limit_utc = (now_utc + timedelta(days=7)).isoformat()

    db = get_db()
    calendar_rows = db.execute(
        "SELECT created_at, raw_text FROM notes WHERE tags LIKE '%\"calendar\"%' AND created_at >= ? AND created_at <= ? ORDER BY created_at ASC",
        (now_utc.isoformat(), limit_utc)
    ).fetchall()

    schedule_context = ""
    if calendar_rows:
        schedule_context = "\nUpcoming Calendar Schedule (Next 7 Days):\n" + "\n".join(
            f"- [{r['created_at']}] {r['raw_text']}" for r in calendar_rows
        )

    if not matches:
        db.close()
        # Answer using schedule context even if vector search matches are empty
        answer = claude_service.answer_query(req.text, [], req.history, schedule_context)
        return QueryResponse(query=req.text, answer=answer, sources=[])

    ids = [m["id"] for m in matches]
    placeholders = ",".join("?" * len(ids))
    rows = db.execute(f"SELECT * FROM notes WHERE id IN ({placeholders})", ids).fetchall()
    db.close()

    row_map = {r["id"]: r for r in rows}
    sources = [
        NoteResponse(
            id=m["id"],
            created_at=m["created_at"],
            raw_text=m["raw_text"],
            tags=json.loads(row_map[m["id"]]["tags"]) if m["id"] in row_map else [],
            summary=row_map[m["id"]]["summary"] if m["id"] in row_map else "",
        )
        for m in matches if m["id"] in row_map
    ]

    answer = claude_service.answer_query(req.text, [s.model_dump() for s in sources], req.history, schedule_context)
    return QueryResponse(query=req.text, answer=answer, sources=sources)


@router.post("/query/stream", dependencies=[Depends(verify_key)])
def query_notes_stream(req: QueryRequest):
    search_query = claude_service.rewrite_query(req.text, req.history)
    matches = chroma_service.search_notes(search_query)

    from datetime import datetime, timezone, timedelta
    now_utc = datetime.now(timezone.utc)
    limit_utc = (now_utc + timedelta(days=7)).isoformat()

    db = get_db()
    calendar_rows = db.execute(
        "SELECT created_at, raw_text FROM notes WHERE id LIKE 'calendar-%' AND created_at >= ? AND created_at <= ? ORDER BY created_at ASC",
        (now_utc.isoformat(), limit_utc)
    ).fetchall()
    schedule_context = ""
    if calendar_rows:
        schedule_context = "\nUpcoming Calendar Schedule (Next 7 Days):\n" + "\n".join(
            f"- [{r['created_at']}] {r['raw_text']}" for r in calendar_rows
        )

    sources = []
    if matches:
        ids = [m["id"] for m in matches]
        placeholders = ",".join("?" * len(ids))
        rows = db.execute(f"SELECT * FROM notes WHERE id IN ({placeholders})", ids).fetchall()
        row_map = {r["id"]: r for r in rows}
        sources = [
            NoteResponse(
                id=m["id"],
                created_at=m["created_at"],
                raw_text=m["raw_text"],
                tags=json.loads(row_map[m["id"]]["tags"]) if m["id"] in row_map else [],
                summary=row_map[m["id"]]["summary"] if m["id"] in row_map else "",
            )
            for m in matches if m["id"] in row_map
        ]
    db.close()

    sources_data = [s.model_dump() for s in sources]

    def generate():
        yield f"data: {json.dumps({'type': 'meta', 'query': req.text, 'sources': sources_data})}\n\n"
        for chunk in claude_service.stream_answer_query(req.text, sources_data, req.history, schedule_context):
            yield f"data: {json.dumps({'type': 'text', 'delta': chunk})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/query/voice", response_model=QueryResponse, dependencies=[Depends(verify_key)])
async def query_notes_voice(audio: UploadFile = File(...), history: str = Form("[]")):
    suffix = os.path.splitext(audio.filename or "audio.webm")[1] or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        async with aiofiles.open(tmp.name, "wb") as f:
            await f.write(await audio.read())
        tmp_path = tmp.name

    try:
        text = whisper_service.transcribe(tmp_path)
    finally:
        os.unlink(tmp_path)

    try:
        history_list = json.loads(history)
    except Exception:
        history_list = []

    return query_notes(QueryRequest(text=text, history=history_list))


class NoteGroupResponse(BaseModel):
    topic: str
    summary: str
    note_ids: list[str]


class MergeGroupRequest(BaseModel):
    note_ids: list[str]
    topic: str
    summary: str


def _classify_notes(notes_list: list[dict]) -> tuple[list[str], list[str], list[dict]]:
    """Return (programmatic_trash_ids, llm_trash_ids, active_notes) without deleting anything."""
    NOISE = {
        "you", "thank you", "bye", "bye bye", "goodbye", "hello", "hi", "ok",
        "okay", "yeah", "yes", "no", "uh", "um", "ah", "oh", "thanks", "yep",
        "yup", "testing", "test", "testing testing", "thank you for watching", "watching"
    }
    programmatic_trash_ids = []
    active_notes = []
    for note in notes_list:
        text = note["raw_text"].strip()
        cleaned = text.lower().rstrip(".").rstrip("?").rstrip("!").strip()
        if not text or cleaned in NOISE:
            programmatic_trash_ids.append(note["id"])
        else:
            active_notes.append(note)

    result = claude_service.cluster_notes(active_notes)
    llm_trash_ids = result.get("trash_note_ids", [])
    groups = result.get("groups", [])
    return programmatic_trash_ids, llm_trash_ids, groups


def _delete_notes(note_ids: list[str]):
    if not note_ids:
        return
    db = get_db()
    placeholders = ",".join("?" * len(note_ids))
    db.execute(f"DELETE FROM notes WHERE id IN ({placeholders})", note_ids)
    db.commit()
    db.close()
    for nid in note_ids:
        try:
            chroma_service.delete_note(nid)
        except Exception as e:
            print(f"Error deleting note {nid} from Chroma: {e}")


class NoteGroupsResponse(BaseModel):
    groups: list[NoteGroupResponse]
    trash_ids: list[str]


@router.get("/groups", response_model=NoteGroupsResponse, dependencies=[Depends(verify_key)])
def list_note_groups():
    """Read-only: clusters notes and identifies trash, but does NOT delete anything."""
    db = get_db()
    rows = db.execute("SELECT * FROM notes WHERE id NOT LIKE 'calendar-%'").fetchall()
    db.close()

    notes_list = [
        {
            "id": r["id"],
            "created_at": r["created_at"],
            "raw_text": r["raw_text"],
            "tags": json.loads(r["tags"]),
            "summary": r["summary"],
        }
        for r in rows
    ]

    programmatic_trash_ids, llm_trash_ids, groups = _classify_notes(notes_list)
    all_trash_ids = programmatic_trash_ids + llm_trash_ids

    return NoteGroupsResponse(
        groups=[NoteGroupResponse(topic=g["topic"], summary=g["summary"], note_ids=g["note_ids"]) for g in groups],
        trash_ids=all_trash_ids,
    )


@router.post("/groups/cleanup", dependencies=[Depends(verify_key)])
def cleanup_trash_notes(body: dict):
    """Delete the given note IDs (user explicitly confirms trash before calling this)."""
    note_ids = body.get("note_ids", [])
    if not note_ids:
        return {"deleted": 0}
    _delete_notes(note_ids)
    return {"deleted": len(note_ids)}


@router.post("/merge-group", response_model=NoteResponse, dependencies=[Depends(verify_key)])
def merge_note_group(req: MergeGroupRequest):
    if len(req.note_ids) < 2:
        raise HTTPException(status_code=400, detail="Must select at least two notes to merge")
        
    db = get_db()
    placeholders = ",".join("?" * len(req.note_ids))
    rows = db.execute(f"SELECT * FROM notes WHERE id IN ({placeholders})", req.note_ids).fetchall()
    
    if len(rows) < len(req.note_ids):
        db.close()
        raise HTTPException(status_code=400, detail="Some notes were not found")
        
    notes_list = [
        {
            "id": r["id"],
            "created_at": r["created_at"],
            "raw_text": r["raw_text"],
            "tags": json.loads(r["tags"]),
            "summary": r["summary"],
        }
        for r in rows
    ]
    
    # Synthesize unified text
    unified_text = claude_service.synthesize_merged_note(notes_list)
    
    # Generate tags/summary for unified text
    analysis = claude_service.tag_note(unified_text)
    tags = analysis["tags"]
    summary = analysis["summary"] or req.summary

    # Save the consolidated note
    note_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    db.execute(
        "INSERT INTO notes (id, created_at, raw_text, tags, summary) VALUES (?, ?, ?, ?, ?)",
        (note_id, created_at, unified_text, json.dumps(tags), summary),
    )

    # Delete the old notes
    db.execute(f"DELETE FROM notes WHERE id IN ({placeholders})", req.note_ids)
    db.commit()
    db.close()

    # Update Vector Store
    chroma_service.add_note(note_id, unified_text, {"created_at": created_at, "tags": json.dumps(tags), "summary": summary})
    for old_id in req.note_ids:
        chroma_service.delete_note(old_id)

    return NoteResponse(id=note_id, created_at=created_at, raw_text=unified_text, tags=tags, summary=summary)

