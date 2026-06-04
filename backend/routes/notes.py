import json
import uuid
import tempfile
import os
from datetime import datetime, timezone

import aiofiles
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
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


class QueryRequest(BaseModel):
    text: str
    history: list[dict] = []


class QueryResponse(BaseModel):
    query: str
    answer: str
    sources: list[NoteResponse]


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

    # If this note indicates a reminder scheduling request, create the reminder record
    if analysis["is_reminder"] and analysis["reminder_details"]:
        rem_details = analysis["reminder_details"]
        reminder_id = str(uuid.uuid4())
        db = get_db()
        db.execute(
            "INSERT INTO reminders (id, title, remind_at, created_at) VALUES (?, ?, ?, ?)",
            (reminder_id, rem_details["title"], rem_details["remind_at"], created_at),
        )
        db.commit()
        db.close()
        
        # Sync reminder to Google Calendar if connected
        from services import google_calendar
        from datetime import timedelta
        if google_calendar.is_connected():
            try:
                end_iso = (datetime.fromisoformat(rem_details["remind_at"]) + timedelta(hours=1)).isoformat()
                event_id = google_calendar.create_event(rem_details["title"], rem_details["remind_at"], end_iso)
                db = get_db()
                db.execute("UPDATE reminders SET google_event_id = ? WHERE id = ?", (event_id, reminder_id))
                db.commit()
                db.close()
            except Exception as e:
                print(f"Failed to sync auto-reminder to Google Calendar: {e}")

    return NoteResponse(id=note_id, created_at=created_at, raw_text=text, tags=tags, summary=summary)


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


@router.post("/query", response_model=QueryResponse, dependencies=[Depends(verify_key)])
def query_notes(req: QueryRequest):
    # Rewrite the search query for vector retrieval using history if present
    search_query = claude_service.rewrite_query(req.text, req.history)
    matches = chroma_service.search_notes(search_query)
    if not matches:
        return QueryResponse(query=req.text, answer="I couldn't find any relevant notes.", sources=[])

    ids = [m["id"] for m in matches]
    db = get_db()
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

    answer = claude_service.answer_query(req.text, [s.model_dump() for s in sources], req.history)
    return QueryResponse(query=req.text, answer=answer, sources=sources)


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


@router.get("/groups", response_model=list[NoteGroupResponse], dependencies=[Depends(verify_key)])
def list_note_groups():
    db = get_db()
    rows = db.execute("SELECT * FROM notes WHERE tags NOT LIKE '%\"calendar\"%'").fetchall()
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
    groups = claude_service.cluster_notes(notes_list)
    return [
        NoteGroupResponse(
            topic=g["topic"],
            summary=g["summary"],
            note_ids=g["note_ids"]
        )
        for g in groups
    ]


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
    
    # Save the consolidated note
    note_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    
    db.execute(
        "INSERT INTO notes (id, created_at, raw_text, tags, summary) VALUES (?, ?, ?, ?, ?)",
        (note_id, created_at, unified_text, json.dumps(tags), req.summary),
    )
    
    # Delete the old notes
    db.execute(f"DELETE FROM notes WHERE id IN ({placeholders})", req.note_ids)
    db.commit()
    db.close()
    
    # Update Vector Store
    chroma_service.add_note(note_id, unified_text, {"created_at": created_at, "tags": json.dumps(tags), "summary": req.summary})
    for old_id in req.note_ids:
        chroma_service.delete_note(old_id)
        
    return NoteResponse(id=note_id, created_at=created_at, raw_text=unified_text, tags=tags, summary=req.summary)

