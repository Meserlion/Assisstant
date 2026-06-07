import asyncio
import hashlib
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
    pinned: bool = False
    archived: bool = False
    color: str | None = None
    audio_url: str | None = None


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


class PinRequest(BaseModel):
    pinned: bool


# Allowed preset colour names (matches frontend swatch picker). None clears the colour.
ALLOWED_COLORS = {"red", "orange", "yellow", "green", "blue", "purple"}


class ColorRequest(BaseModel):
    color: str | None = None


class CleanupRequest(BaseModel):
    note_ids: list[str] = []


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

    try:
        chroma_service.add_note(note_id, text, {"created_at": created_at, "tags": json.dumps(tags), "summary": summary})
    except Exception as e:
        print(f"CHROMA_SYNC_FAILURE note_id={note_id} error={e} — rolling back SQLite insert")
        try:
            db = get_db()
            db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            db.commit()
            db.close()
        except Exception as rb_err:
            print(f"CHROMA_ROLLBACK_FAILURE note_id={note_id} rollback_error={rb_err}")
        raise HTTPException(status_code=500, detail="Failed to index note for search. Note was not saved.")

    audio_path = None  # populated by capture endpoint when audio is saved

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

    return NoteResponse(id=note_id, created_at=created_at, raw_text=text, tags=tags, summary=summary, pinned=False, archived=False, audio_url=None)


@router.post("/capture", response_model=NoteResponse, dependencies=[Depends(verify_key)])
async def capture_note(
    audio: UploadFile = File(...),
    client_timezone: str = Form(None),
    client_local_time: str = Form(None)
):
    suffix = os.path.splitext(audio.filename or "audio.webm")[1] or ".webm"
    audio_bytes = await audio.read()

    # Transcribe from a temp file
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        text = whisper_service.transcribe(tmp_path)
    finally:
        os.unlink(tmp_path)

    note = await asyncio.to_thread(_save_note_from_text, text, client_timezone, client_local_time)

    # Persist audio for playback — use absolute path so FileResponse works regardless of CWD
    audio_dir = os.path.abspath(os.path.join(os.path.dirname(settings.sqlite_db_path), "audio"))
    os.makedirs(audio_dir, exist_ok=True)
    audio_path = os.path.join(audio_dir, f"{note.id}{suffix}")
    with open(audio_path, "wb") as f:
        f.write(audio_bytes)

    # MediaRecorder WebM files lack duration metadata, causing browsers to show 0:00.
    # Remux with ffmpeg (-c copy, no re-encode) to write a proper duration into the header.
    import subprocess
    remux_path = audio_path + ".remux" + suffix
    try:
        proc = subprocess.run(
            ["ffmpeg", "-y", "-i", audio_path, "-c", "copy", remux_path],
            capture_output=True, timeout=30
        )
        if proc.returncode == 0 and os.path.exists(remux_path) and os.path.getsize(remux_path) > 0:
            os.replace(remux_path, audio_path)
    except Exception:
        pass
    finally:
        if os.path.exists(remux_path):
            try:
                os.unlink(remux_path)
            except Exception:
                pass

    db = get_db()
    db.execute("UPDATE notes SET audio_path = ? WHERE id = ?", (audio_path, note.id))
    db.commit()
    db.close()

    return NoteResponse(**{**note.model_dump(), "audio_url": f"/api/notes/{note.id}/audio"})


@router.post("/image", response_model=NoteResponse, dependencies=[Depends(verify_key)])
async def capture_image_note(
    image: UploadFile = File(...),
    client_timezone: str = Form(None),
    client_local_time: str = Form(None)
):
    """Accept an image upload, describe it with Claude Vision, and save as a text note."""
    image_bytes = await image.read()
    mime_type = image.content_type or "image/jpeg"
    # Normalise MIME — some browsers send image/jpg instead of image/jpeg
    if mime_type == "image/jpg":
        mime_type = "image/jpeg"
    # Claude Vision supports jpeg, png, gif, webp
    supported = {"image/jpeg", "image/png", "image/gif", "image/webp"}
    if mime_type not in supported:
        raise HTTPException(status_code=400, detail=f"Unsupported image type: {mime_type}. Use JPEG, PNG, GIF or WebP.")
    try:
        text = claude_service.describe_image(image_bytes, mime_type)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Image analysis failed: {exc}")
    return await asyncio.to_thread(_save_note_from_text, text, client_timezone, client_local_time)


class TextNoteRequest(BaseModel):
    text: str
    client_timezone: str = None
    client_local_time: str = None


@router.post("/text", response_model=NoteResponse, dependencies=[Depends(verify_key)])
def create_text_note(req: TextNoteRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Note text cannot be empty")
    return _save_note_from_text(req.text.strip(), req.client_timezone, req.client_local_time)


def _row_to_note(r) -> NoteResponse:
    return NoteResponse(
        id=r["id"],
        created_at=r["created_at"],
        raw_text=r["raw_text"],
        tags=json.loads(r["tags"]),
        summary=r["summary"],
        pinned=bool(r["pinned"]),
        archived=bool(r["archived"]),
        color=(r["color"] if "color" in r.keys() else None),
        audio_url=f"/api/notes/{r['id']}/audio" if r["audio_path"] else None,
    )


@router.get("/", response_model=list[NoteResponse], dependencies=[Depends(verify_key)])
def list_notes(limit: int = 50, offset: int = 0, archived: bool = False):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM notes WHERE tags NOT LIKE '%\"calendar\"%' AND archived = ? ORDER BY pinned DESC, created_at DESC LIMIT ? OFFSET ?",
        (int(archived), limit, offset)
    ).fetchall()
    db.close()
    return [_row_to_note(r) for r in rows]


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


@router.patch("/{note_id}/pin", response_model=NoteResponse, dependencies=[Depends(verify_key)])
def pin_note(note_id: str, body: PinRequest):
    pinned = int(body.pinned)
    db = get_db()
    db.execute("UPDATE notes SET pinned = ? WHERE id = ?", (pinned, note_id))
    db.commit()
    row = db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    db.close()
    if not row:
        raise HTTPException(status_code=404, detail="Note not found")
    return _row_to_note(row)


@router.patch("/{note_id}/color", response_model=NoteResponse, dependencies=[Depends(verify_key)])
def color_note(note_id: str, body: ColorRequest):
    color = body.color
    if color is not None and color not in ALLOWED_COLORS:
        raise HTTPException(status_code=400, detail=f"Invalid color. Allowed: {', '.join(sorted(ALLOWED_COLORS))}")
    db = get_db()
    db.execute("UPDATE notes SET color = ? WHERE id = ?", (color, note_id))
    db.commit()
    row = db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    db.close()
    if not row:
        raise HTTPException(status_code=404, detail="Note not found")
    return _row_to_note(row)


class ArchiveRequest(BaseModel):
    archived: bool


@router.patch("/{note_id}/archive", response_model=NoteResponse, dependencies=[Depends(verify_key)])
def archive_note(note_id: str, body: ArchiveRequest):
    db = get_db()
    db.execute("UPDATE notes SET archived = ? WHERE id = ?", (int(body.archived), note_id))
    db.commit()
    row = db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    db.close()
    if not row:
        raise HTTPException(status_code=404, detail="Note not found")
    return _row_to_note(row)


@router.get("/{note_id}/audio")
def get_note_audio(note_id: str, key: str = ""):
    """Audio endpoint accepts the API key as a query param so the browser's
    native <audio> element (which cannot send custom headers) can authenticate."""
    from fastapi.responses import FileResponse
    from fastapi.security import APIKeyHeader as _H
    if key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    db = get_db()
    row = db.execute("SELECT audio_path FROM notes WHERE id = ?", (note_id,)).fetchone()
    db.close()
    if not row or not row["audio_path"]:
        raise HTTPException(status_code=404, detail="No audio for this note")
    if not os.path.exists(row["audio_path"]):
        raise HTTPException(status_code=404, detail="Audio file missing")
    # Explicit extension→MIME map so minimal Linux installs (where mimetypes may not
    # know .webm or .mp4) always serve the correct audio content type.
    _EXT_MIME = {
        ".webm": "audio/webm",
        ".mp4":  "audio/mp4",
        ".m4a":  "audio/mp4",
        ".ogg":  "audio/ogg",
        ".oga":  "audio/ogg",
        ".wav":  "audio/wav",
        ".mp3":  "audio/mpeg",
    }
    _, ext = os.path.splitext(row["audio_path"])
    mime = _EXT_MIME.get(ext.lower())
    if not mime:
        import mimetypes
        mime, _ = mimetypes.guess_type(row["audio_path"])
        # mimetypes returns video/* for .mp4/.webm; browsers won't play those in <audio>.
        if mime and mime.startswith("video/"):
            mime = "audio/" + mime.split("/")[1]
        mime = mime or "audio/webm"
    return FileResponse(row["audio_path"], media_type=mime, headers={"Accept-Ranges": "bytes"})


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
    updated_row = db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    db.close()

    # Update Vector Store (Chroma)
    chroma_service.delete_note(note_id)
    chroma_service.add_note(note_id, req.text, {"created_at": row["created_at"], "tags": json.dumps(tags), "summary": summary})

    return _row_to_note(updated_row)



@router.post("/{note_id}/research", response_model=NoteResponse, dependencies=[Depends(verify_key)])
def research_note(note_id: str):
    db = get_db()
    row = db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    if not row:
        db.close()
        raise HTTPException(status_code=404, detail="Note not found")

    research = claude_service.research_note(row["raw_text"])
    if not research:
        db.close()
        return NoteResponse(
            id=note_id, created_at=row["created_at"], raw_text=row["raw_text"],
            tags=json.loads(row["tags"]), summary=row["summary"],
            pinned=bool(row["pinned"]), archived=bool(row["archived"]),
            audio_url=f"/api/notes/{note_id}/audio" if row["audio_path"] else None
        )

    new_text = row["raw_text"].rstrip() + "\n\n**Research:**\n" + research
    analysis = claude_service.tag_note(new_text)
    tags = analysis["tags"]
    summary = analysis["summary"]

    db.execute(
        "UPDATE notes SET raw_text = ?, tags = ?, summary = ? WHERE id = ?",
        (new_text, json.dumps(tags), summary, note_id)
    )
    db.commit()
    db.close()

    chroma_service.delete_note(note_id)
    chroma_service.add_note(note_id, new_text, {"created_at": row["created_at"], "tags": json.dumps(tags), "summary": summary})

    return NoteResponse(
        id=note_id, created_at=row["created_at"], raw_text=new_text,
        tags=tags, summary=summary,
        pinned=bool(row["pinned"]), archived=bool(row["archived"]),
        audio_url=f"/api/notes/{note_id}/audio" if row["audio_path"] else None
    )


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
        "SELECT created_at, raw_text FROM notes WHERE tags LIKE '%\"calendar\"%' AND created_at >= ? AND created_at <= ? ORDER BY created_at ASC",
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



_groups_cache: dict = {"fingerprint": None, "result": None}


def _notes_fingerprint(notes_list: list[dict]) -> str:
    key = sorted((n["id"], n["raw_text"]) for n in notes_list)
    return hashlib.md5(json.dumps(key).encode()).hexdigest()


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
def list_note_groups(include_archived: bool = False):
    """Read-only: clusters notes and identifies trash, but does NOT delete anything."""
    db = get_db()
    if include_archived:
        rows = db.execute("SELECT * FROM notes WHERE tags NOT LIKE '%\"calendar\"%'").fetchall()
    else:
        rows = db.execute("SELECT * FROM notes WHERE tags NOT LIKE '%\"calendar\"%' AND archived = 0").fetchall()
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

    fp = _notes_fingerprint(notes_list)
    if fp == _groups_cache["fingerprint"] and _groups_cache["result"] is not None:
        return _groups_cache["result"]

    programmatic_trash_ids, llm_trash_ids, groups = _classify_notes(notes_list)
    all_trash_ids = programmatic_trash_ids + llm_trash_ids

    result = NoteGroupsResponse(
        groups=[NoteGroupResponse(topic=g["topic"], summary=g["summary"], note_ids=g["note_ids"]) for g in groups],
        trash_ids=all_trash_ids,
    )
    _groups_cache["fingerprint"] = fp
    _groups_cache["result"] = result
    return result


@router.post("/groups/cleanup", dependencies=[Depends(verify_key)])
def cleanup_trash_notes(body: CleanupRequest):
    """Delete the given note IDs (user explicitly confirms trash before calling this)."""
    note_ids = body.note_ids
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

    # Save the consolidated note — always as a new (non-archived) note so it
    # surfaces in the main feed regardless of the archived status of source notes.
    note_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    db.execute(
        "INSERT INTO notes (id, created_at, raw_text, tags, summary, archived) VALUES (?, ?, ?, ?, ?, ?)",
        (note_id, created_at, unified_text, json.dumps(tags), summary, 0),
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
