import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from typing import Optional
from google_auth_oauthlib.flow import Flow

from config import settings
from database import get_db
from services import google_calendar, push_service
from services.claude_service import client as anthropic_client

router = APIRouter(prefix="/calendar", tags=["calendar"])
api_key_header = APIKeyHeader(name="X-API-Key")

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def verify_key(key: str = Depends(api_key_header)):
    if key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


class ReminderRequest(BaseModel):
    text: str
    selected_date: Optional[str] = None  # Format: YYYY-MM-DD
    client_timezone: Optional[str] = None
    client_local_time: Optional[str] = None


class EventCreate(BaseModel):
    title: str
    start_iso: str
    end_iso: str
    description: str = ""
    set_reminder: bool = True


@router.get("/oauth/start", dependencies=[Depends(verify_key)])
def oauth_start():
    if not settings.google_client_id:
        raise HTTPException(status_code=400, detail="Google OAuth not configured")
    flow = Flow.from_client_config(
        {"web": {"client_id": settings.google_client_id, "client_secret": settings.google_client_secret,
                 "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                 "token_uri": "https://oauth2.googleapis.com/token"}},
        scopes=SCOPES,
        redirect_uri=settings.google_redirect_uri,
    )
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
    return {"url": auth_url}


@router.get("/oauth/callback")
def oauth_callback(code: str = None, error: str = None):
    if error:
        print(f"OAuth Callback Error from Google: {error}")
        return RedirectResponse(url="/?error=" + error)
    if not code:
        print("OAuth Callback: No code parameter received")
        return RedirectResponse(url="/?error=missing_code")
    try:
        google_calendar.store_credentials_from_code(
            code, settings.google_client_id, settings.google_client_secret, settings.google_redirect_uri
        )
        return RedirectResponse(url="/?connected=1")
    except Exception as e:
        print(f"OAuth Callback exception during token exchange: {str(e)}")
        return RedirectResponse(url="/?error=token_exchange_failed")


@router.get("/status", dependencies=[Depends(verify_key)])
def calendar_status():
    return {"connected": google_calendar.is_connected()}


def sync_calendar_events_to_notes(events: list[dict]):
    import json
    from database import get_db
    from services import chroma_service
    
    db = get_db()
    for event in events:
        event_id = event["id"]
        note_id = f"calendar-{event_id}"
        title = event.get("title", "")
        start = event.get("start", "")
        desc = event.get("description", "") or ""
        
        raw_text = f"Google Calendar Event: {title}\nDate/Time: {start}\nDescription: {desc}"
        summary = f"Calendar event: {title}"
        tags = ["calendar"]
        
        row = db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        if not row:
            db.execute(
                "INSERT INTO notes (id, created_at, raw_text, tags, summary) VALUES (?, ?, ?, ?, ?)",
                (note_id, start, raw_text, json.dumps(tags), summary),
            )
            chroma_service.add_note(note_id, raw_text, {"created_at": start, "tags": json.dumps(tags), "summary": summary})
        else:
            if row["raw_text"] != raw_text or row["summary"] != summary:
                db.execute(
                    "UPDATE notes SET raw_text = ?, summary = ? WHERE id = ?",
                    (raw_text, summary, note_id),
                )
                chroma_service.delete_note(note_id)
                chroma_service.add_note(note_id, raw_text, {"created_at": start, "tags": json.dumps(tags), "summary": summary})
    db.commit()
    db.close()


@router.get("/events", dependencies=[Depends(verify_key)])
def get_events():
    if not google_calendar.is_connected():
        raise HTTPException(status_code=400, detail="Google Calendar not connected")
    events = google_calendar.list_events()
    try:
        sync_calendar_events_to_notes(events)
    except Exception as e:
        print(f"Error syncing calendar events to notes: {e}")
    return events


@router.post("/events", dependencies=[Depends(verify_key)])
def create_event(req: EventCreate):
    event_id = google_calendar.create_event(req.title, req.start_iso, req.end_iso, req.description)
    if req.set_reminder:
        _create_reminder(req.title, req.start_iso, event_id)
    return {"event_id": event_id}


@router.post("/reminder/voice", dependencies=[Depends(verify_key)])
async def create_reminder_from_text(req: ReminderRequest):
    parsed = _parse_reminder(req.text, req.selected_date, req.client_timezone, req.client_local_time)
    if not parsed:
        raise HTTPException(status_code=422, detail="Could not understand the reminder")

    reminder_id = str(uuid.uuid4())
    db = get_db()
    db.execute(
        "INSERT INTO reminders (id, title, remind_at, created_at) VALUES (?, ?, ?, ?)",
        (reminder_id, parsed["title"], parsed["remind_at"], datetime.now(timezone.utc).isoformat()),
    )
    db.commit()
    db.close()

    event_id = None
    if google_calendar.is_connected():
        end_iso = (datetime.fromisoformat(parsed["remind_at"]) + timedelta(hours=1)).isoformat()
        event_id = google_calendar.create_event(parsed["title"], parsed["remind_at"], end_iso)
        db = get_db()
        db.execute("UPDATE reminders SET google_event_id = ? WHERE id = ?", (event_id, reminder_id))
        db.commit()
        db.close()

    return {"id": reminder_id, "title": parsed["title"], "remind_at": parsed["remind_at"], "google_event_id": event_id}


@router.get("/reminders", dependencies=[Depends(verify_key)])
def list_reminders():
    db = get_db()
    rows = db.execute("SELECT * FROM reminders ORDER BY remind_at ASC").fetchall()
    db.close()
    return [dict(r) for r in rows]


@router.delete("/reminders/{reminder_id}", dependencies=[Depends(verify_key)])
def delete_reminder(reminder_id: str):
    db = get_db()
    db.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
    db.commit()
    db.close()
    return {"deleted": reminder_id}


@router.post("/reminders/{reminder_id}/snooze", dependencies=[Depends(verify_key)])
def snooze_reminder(reminder_id: str):
    db = get_db()
    row = db.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
    if not row:
        db.close()
        raise HTTPException(status_code=404, detail="Reminder not found")
    
    new_time = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    db.execute(
        "UPDATE reminders SET remind_at = ?, sent = 0 WHERE id = ?",
        (new_time, reminder_id),
    )
    db.commit()
    db.close()
    return {"status": "snoozed", "remind_at": new_time}


@router.post("/reminders/{reminder_id}/done", dependencies=[Depends(verify_key)])
def done_reminder(reminder_id: str):
    db = get_db()
    row = db.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
    if not row:
        db.close()
        raise HTTPException(status_code=404, detail="Reminder not found")
    
    db.execute("UPDATE reminders SET sent = 1 WHERE id = ?", (reminder_id,))
    db.commit()
    db.close()
    return {"status": "done"}


@router.post("/reminders/{reminder_id}/undone", dependencies=[Depends(verify_key)])
def undone_reminder(reminder_id: str):
    db = get_db()
    row = db.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
    if not row:
        db.close()
        raise HTTPException(status_code=404, detail="Reminder not found")
    
    db.execute("UPDATE reminders SET sent = 0 WHERE id = ?", (reminder_id,))
    db.commit()
    db.close()
    return {"status": "active"}


@router.delete("/events/{event_id}", dependencies=[Depends(verify_key)])
def delete_event(event_id: str):
    if not google_calendar.is_connected():
        raise HTTPException(status_code=400, detail="Google Calendar not connected")
    try:
        google_calendar.delete_event(event_id)
        # Clean up any cached event note from local databases
        note_id = f"calendar-{event_id}"
        db = get_db()
        db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        db.commit()
        db.close()
        try:
            from services import chroma_service
            chroma_service.delete_note(note_id)
        except Exception:
            pass
        return {"deleted": event_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _create_reminder(title: str, remind_at: str, event_id: str = None):
    reminder_id = str(uuid.uuid4())
    db = get_db()
    db.execute(
        "INSERT INTO reminders (id, title, remind_at, google_event_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (reminder_id, title, remind_at, event_id, datetime.now(timezone.utc).isoformat()),
    )
    db.commit()
    db.close()


def _parse_reminder(text: str, selected_date: str = None, client_timezone: str = None, client_local_time: str = None) -> dict | None:
    now = datetime.now(timezone.utc).isoformat()
    context = f"Current time (UTC): {now}\n"
    if client_local_time:
        context += f"The user's local time is: {client_local_time}\n"
    if client_timezone:
        context += f"The user's local timezone is: {client_timezone}\n"
    if selected_date:
        context += f"The user has selected the date: {selected_date} in the calendar. Any relative time expressions without a specific date (e.g. 'at 3pm', 'in the afternoon') should be scheduled on this selected date: {selected_date}.\n"
        
    response = anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=128,
        messages=[{
            "role": "user",
            "content": (
                f"{context}"
                f"Parse this reminder request into JSON with 'title' and 'remind_at' (ISO 8601 UTC). "
                f"Return only valid JSON, nothing else.\n\nRequest: {text}"
            )
        }]
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        import json
        return json.loads(raw)
    except Exception:
        return None
