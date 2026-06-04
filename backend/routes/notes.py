import json
import uuid
import tempfile
import os
from datetime import datetime, timezone

import aiofiles
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
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


class QueryResponse(BaseModel):
    answer: str
    sources: list[NoteResponse]


@router.post("/capture", response_model=NoteResponse, dependencies=[Depends(verify_key)])
async def capture_note(audio: UploadFile = File(...)):
    suffix = os.path.splitext(audio.filename or "audio.webm")[1] or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        async with aiofiles.open(tmp.name, "wb") as f:
            await f.write(await audio.read())
        tmp_path = tmp.name

    try:
        text = whisper_service.transcribe(tmp_path)
    finally:
        os.unlink(tmp_path)

    tags, summary = claude_service.tag_note(text)
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

    return NoteResponse(id=note_id, created_at=created_at, raw_text=text, tags=tags, summary=summary)


@router.get("/", response_model=list[NoteResponse], dependencies=[Depends(verify_key)])
def list_notes(limit: int = 50, offset: int = 0):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM notes ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)
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
    matches = chroma_service.search_notes(req.text)
    if not matches:
        return QueryResponse(answer="I couldn't find any relevant notes.", sources=[])

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

    answer = claude_service.answer_query(req.text, [s.model_dump() for s in sources])
    return QueryResponse(answer=answer, sources=sources)


@router.post("/query/voice", response_model=QueryResponse, dependencies=[Depends(verify_key)])
async def query_notes_voice(audio: UploadFile = File(...)):
    suffix = os.path.splitext(audio.filename or "audio.webm")[1] or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        async with aiofiles.open(tmp.name, "wb") as f:
            await f.write(await audio.read())
        tmp_path = tmp.name

    try:
        text = whisper_service.transcribe(tmp_path)
    finally:
        os.unlink(tmp_path)

    return query_notes(QueryRequest(text=text))
