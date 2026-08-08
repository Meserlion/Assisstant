#!/usr/bin/env python3
"""
MCP Server for the personal Assistant app.

Exposes notes management tools (list, create, update, delete, search, pin, archive)
so Claude desktop can read and write notes directly.

Configuration via environment variables:
  ASSISTANT_BASE_URL  — base URL of the running backend (default: http://localhost:8000)
  ASSISTANT_API_KEY   — API key set in the backend .env file
"""

import json
import os
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Server init & config
# ---------------------------------------------------------------------------

mcp = FastMCP("assistant_mcp")

BASE_URL = os.environ.get("ASSISTANT_BASE_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.environ.get("ASSISTANT_API_KEY", "")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _headers() -> dict:
    return {"X-API-Key": API_KEY}


async def _get(path: str, **params) -> dict | list:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/api{path}", headers=_headers(), params=params, timeout=30.0)
        r.raise_for_status()
        return r.json()


async def _post(path: str, json_body: dict) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{BASE_URL}/api{path}", headers=_headers(), json=json_body, timeout=30.0)
        r.raise_for_status()
        return r.json()


async def _put(path: str, json_body: dict) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.put(f"{BASE_URL}/api{path}", headers=_headers(), json=json_body, timeout=30.0)
        r.raise_for_status()
        return r.json()


async def _patch(path: str, json_body: dict) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.patch(f"{BASE_URL}/api{path}", headers=_headers(), json=json_body, timeout=30.0)
        r.raise_for_status()
        return r.json()


async def _delete(path: str) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.delete(f"{BASE_URL}/api{path}", headers=_headers(), timeout=30.0)
        r.raise_for_status()
        return r.json()


def _handle_error(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if code == 401:
            return "Error: Invalid API key. Set ASSISTANT_API_KEY to the key from your backend .env file."
        if code == 404:
            return "Error: Note not found. Check the note ID."
        if code == 400:
            try:
                detail = e.response.json().get("detail", "Bad request")
            except Exception:
                detail = "Bad request"
            return f"Error: {detail}"
        return f"Error: API returned status {code}: {e.response.text[:200]}"
    if isinstance(e, httpx.ConnectError):
        return f"Error: Could not connect to Assistant at {BASE_URL}. Make sure the backend is running."
    if isinstance(e, httpx.TimeoutException):
        return "Error: Request timed out. The backend may be busy."
    return f"Error: {type(e).__name__}: {e}"


def _format_note(note: dict) -> str:
    tags = ", ".join(note.get("tags") or []) or "none"
    pinned = " 📌" if note.get("pinned") else ""
    archived = " [archived]" if note.get("archived") else ""
    created = note.get("created_at", "")[:19].replace("T", " ")
    return (
        f"**ID**: {note['id']}\n"
        f"**Created**: {created}{pinned}{archived}\n"
        f"**Tags**: {tags}\n"
        f"**Summary**: {note.get('summary', '')}\n"
        f"**Text**: {note.get('raw_text', '')}"
    )


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------

class ListNotesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    limit: Optional[int] = Field(default=20, description="Max notes to return (1–100)", ge=1, le=100)
    offset: Optional[int] = Field(default=0, description="Pagination offset", ge=0)
    archived: Optional[bool] = Field(default=False, description="Set true to list archived notes instead")


class CreateNoteInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    text: str = Field(..., description="Full text content of the new note", min_length=1, max_length=10000)


class UpdateNoteInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    note_id: str = Field(..., description="UUID of the note to update", min_length=1)
    text: str = Field(..., description="Replacement text for the note", min_length=1, max_length=10000)


class DeleteNoteInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    note_id: str = Field(..., description="UUID of the note to delete", min_length=1)


class SearchNotesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    query: str = Field(..., description="Natural-language question or search phrase", min_length=1, max_length=500)


class PinNoteInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    note_id: str = Field(..., description="UUID of the note to pin or unpin", min_length=1)
    pinned: bool = Field(..., description="True to pin, False to unpin")


class ArchiveNoteInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    note_id: str = Field(..., description="UUID of the note to archive or unarchive", min_length=1)
    archived: bool = Field(..., description="True to archive, False to restore")


class GetNoteInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    note_id: str = Field(..., description="UUID of the note to retrieve", min_length=1)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool(
    name="assistant_list_notes",
    annotations={
        "title": "List Notes",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def assistant_list_notes(params: ListNotesInput) -> str:
    """List notes from the personal Assistant app, newest first (pinned notes appear first).

    Returns a paginated list of notes with their IDs, creation dates, tags, summaries,
    and full text. Use the note ID for update/delete/pin/archive operations.

    Args:
        params (ListNotesInput):
            - limit (int): Max notes to return, 1–100 (default 20)
            - offset (int): Pagination offset (default 0)
            - archived (bool): True to list archived notes (default False)

    Returns:
        str: Markdown-formatted list of notes, or an error message.
    """
    try:
        notes = await _get("/notes/", limit=params.limit, offset=params.offset, archived=str(params.archived).lower())
        if not notes:
            label = "archived" if params.archived else "active"
            return f"No {label} notes found."
        lines = [f"## Notes ({len(notes)} returned, offset={params.offset})\n"]
        for note in notes:
            lines.append(_format_note(note))
            lines.append("---")
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="assistant_get_note",
    annotations={
        "title": "Get Note by ID",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def assistant_get_note(params: GetNoteInput) -> str:
    """Retrieve a single note by its UUID from the personal Assistant app.

    Use this when you already know the note ID and want its full details.

    Args:
        params (GetNoteInput):
            - note_id (str): UUID of the note

    Returns:
        str: Markdown-formatted note details, or an error message.
    """
    try:
        # The backend has no single-note GET; search active and archived lists
        for archived in (False, True):
            notes = await _get("/notes/", limit=100, offset=0, archived=str(archived).lower())
            for note in notes:
                if note["id"] == params.note_id:
                    return _format_note(note)
        return f"Error: Note {params.note_id} not found."
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="assistant_create_note",
    annotations={
        "title": "Create Note",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def assistant_create_note(params: CreateNoteInput) -> str:
    """Create a new text note in the personal Assistant app.

    The backend automatically generates tags and a summary using Claude Haiku,
    and will schedule a reminder if the note text looks like a reminder request.

    Args:
        params (CreateNoteInput):
            - text (str): Full note content

    Returns:
        str: The newly created note, or an error message.

    Example:
        - "Remind me to call John tomorrow at 3pm" → creates note + reminder
        - "Meeting notes: ..." → creates tagged note
    """
    try:
        note = await _post("/notes/text", {"text": params.text})
        return f"✅ Note created.\n\n{_format_note(note)}"
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="assistant_update_note",
    annotations={
        "title": "Update Note",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def assistant_update_note(params: UpdateNoteInput) -> str:
    """Replace the text of an existing note in the personal Assistant app.

    Tags and summary are automatically regenerated from the new text.
    The Chroma vector index is also updated so searches stay accurate.

    Args:
        params (UpdateNoteInput):
            - note_id (str): UUID of the note to update
            - text (str): New full text to replace the existing content

    Returns:
        str: The updated note, or an error message.
    """
    try:
        note = await _put(f"/notes/{params.note_id}", {"text": params.text})
        return f"✅ Note updated.\n\n{_format_note(note)}"
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="assistant_delete_note",
    annotations={
        "title": "Delete Note",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def assistant_delete_note(params: DeleteNoteInput) -> str:
    """Permanently delete a note from the personal Assistant app.

    This removes the note from both SQLite and the Chroma vector index.
    This action is IRREVERSIBLE — confirm the note ID before calling.

    Args:
        params (DeleteNoteInput):
            - note_id (str): UUID of the note to delete

    Returns:
        str: Confirmation message, or an error message.
    """
    try:
        result = await _delete(f"/notes/{params.note_id}")
        return f"🗑️ Deleted note {result.get('deleted', params.note_id)}."
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="assistant_search_notes",
    annotations={
        "title": "Search Notes (RAG)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def assistant_search_notes(params: SearchNotesInput) -> str:
    """Semantically search notes and get an AI-synthesised answer with sources.

    Uses vector similarity (ChromaDB) to find relevant notes, then Claude Sonnet
    to compose a grounded answer. Also includes upcoming calendar events.

    Args:
        params (SearchNotesInput):
            - query (str): Natural-language question or topic to search for

    Returns:
        str: AI answer followed by the source notes used, or an error message.

    Examples:
        - "What did I say about the project deadline?"
        - "Do I have anything scheduled for next week?"
        - "Summary of my shopping list notes"
    """
    try:
        result = await _post("/notes/query", {"text": params.query, "history": []})
        answer = result.get("answer", "No answer generated.")
        sources = result.get("sources", [])
        lines = [f"**Answer**: {answer}"]
        if sources:
            lines.append(f"\n**Sources** ({len(sources)} notes):\n")
            for note in sources:
                lines.append(_format_note(note))
                lines.append("---")
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="assistant_pin_note",
    annotations={
        "title": "Pin / Unpin Note",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def assistant_pin_note(params: PinNoteInput) -> str:
    """Pin or unpin a note so it appears at the top of the notes list.

    Args:
        params (PinNoteInput):
            - note_id (str): UUID of the note
            - pinned (bool): True to pin, False to unpin

    Returns:
        str: Updated note, or an error message.
    """
    try:
        note = await _patch(f"/notes/{params.note_id}/pin", {"pinned": params.pinned})
        action = "📌 Pinned" if params.pinned else "Unpinned"
        return f"{action} note.\n\n{_format_note(note)}"
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="assistant_archive_note",
    annotations={
        "title": "Archive / Restore Note",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def assistant_archive_note(params: ArchiveNoteInput) -> str:
    """Archive a note (hide from main list) or restore it.

    Archived notes are not deleted — they can be retrieved with
    assistant_list_notes using archived=True.

    Args:
        params (ArchiveNoteInput):
            - note_id (str): UUID of the note
            - archived (bool): True to archive, False to restore

    Returns:
        str: Updated note, or an error message.
    """
    try:
        note = await _patch(f"/notes/{params.note_id}/archive", {"archived": params.archived})
        action = "📦 Archived" if params.archived else "Restored"
        return f"{action} note.\n\n{_format_note(note)}"
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not API_KEY:
        print("WARNING: ASSISTANT_API_KEY is not set. All requests will fail with 401.")
    mcp.run()
