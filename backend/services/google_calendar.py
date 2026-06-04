import json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from database import get_db

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _save_tokens(creds: Credentials):
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO google_tokens (id, token_json) VALUES (1, ?)",
        (creds.to_json(),),
    )
    db.commit()
    db.close()


def _load_creds() -> Credentials | None:
    db = get_db()
    row = db.execute("SELECT token_json FROM google_tokens WHERE id = 1").fetchone()
    db.close()
    if not row:
        return None
    creds = Credentials.from_authorized_user_info(json.loads(row["token_json"]), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_tokens(creds)
    return creds


def is_connected() -> bool:
    return _load_creds() is not None


def get_service():
    creds = _load_creds()
    if not creds:
        raise RuntimeError("Google Calendar not connected")
    return build("calendar", "v3", credentials=creds)


def list_events(max_results: int = 100) -> list[dict]:
    from datetime import datetime, timezone
    service = get_service()
    now = datetime.now(timezone.utc).isoformat()
    result = service.events().list(
        calendarId="primary",
        timeMin=now,
        maxResults=max_results,
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    events = []
    for e in result.get("items", []):
        start = e["start"].get("dateTime", e["start"].get("date", ""))
        events.append({"id": e["id"], "title": e.get("summary", ""), "start": start, "description": e.get("description", "")})
    return events


def create_event(title: str, start_iso: str, end_iso: str, description: str = "") -> str:
    service = get_service()
    body = {
        "summary": title,
        "description": description,
        "start": {"dateTime": start_iso, "timeZone": "UTC"},
        "end": {"dateTime": end_iso, "timeZone": "UTC"},
    }
    event = service.events().insert(calendarId="primary", body=body).execute()
    return event["id"]


def delete_event(event_id: str):
    service = get_service()
    service.events().delete(calendarId="primary", eventId=event_id).execute()


def store_credentials_from_code(code: str, client_id: str, client_secret: str, redirect_uri: str):
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_config(
        {"web": {"client_id": client_id, "client_secret": client_secret,
                 "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                 "token_uri": "https://oauth2.googleapis.com/token"}},
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )
    flow.fetch_token(code=code)
    _save_tokens(flow.credentials)
