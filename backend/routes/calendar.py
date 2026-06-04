import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
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
def oauth_callback(code: str):
    google_calendar.store_credentials_from_code(
        code, settings.google_client_id, settings.google_client_secret, settings.google_redirect_uri
    )
    return RedirectResponse(url="/?connected=1")


@router.get("/status", dependencies=[Depends(verify_key)])
def calendar_status():
    return {"connected": google_calendar.is_connected()}


@router.get("/events", dependencies=[Depends(verify_key)])
def get_events():
    if not google_calendar.is_connected():
        raise HTTPException(status_code=400, detail="Google Calendar not connected")
    return google_calendar.list_events()


@router.post("/events", dependencies=[Depends(verify_key)])
def create_event(req: EventCreate):
    event_id = google_calendar.create_event(req.title, req.start_iso, req.end_iso, req.description)
    if req.set_reminder:
        _create_reminder(req.title, req.start_iso, event_id)
    return {"event_id": event_id}


@router.post("/reminder/voice", dependencies=[Depends(verify_key)])
async def create_reminder_from_text(req: ReminderRequest):
    parsed = _parse_reminder(req.text)
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
    rows = db.execute("SELECT * FROM reminders WHERE sent = 0 ORDER BY remind_at ASC").fetchall()
    db.close()
    return [dict(r) for r in rows]


@router.delete("/reminders/{reminder_id}", dependencies=[Depends(verify_key)])
def delete_reminder(reminder_id: str):
    db = get_db()
    db.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
    db.commit()
    db.close()
    return {"deleted": reminder_id}


def _create_reminder(title: str, remind_at: str, event_id: str = None):
    reminder_id = str(uuid.uuid4())
    db = get_db()
    db.execute(
        "INSERT INTO reminders (id, title, remind_at, google_event_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (reminder_id, title, remind_at, event_id, datetime.now(timezone.utc).isoformat()),
    )
    db.commit()
    db.close()


def _parse_reminder(text: str) -> dict | None:
    now = datetime.now(timezone.utc).isoformat()
    response = anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=128,
        messages=[{
            "role": "user",
            "content": (
                f"Current time (UTC): {now}\n"
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
