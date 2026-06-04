from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from database import get_db
from services.push_service import send_push

scheduler = BackgroundScheduler()


def check_reminders():
    now = datetime.now(timezone.utc)
    window = (now + timedelta(minutes=1)).isoformat()
    db = get_db()
    due = db.execute(
        "SELECT * FROM reminders WHERE sent = 0 AND remind_at <= ?", (window,)
    ).fetchall()
    for r in due:
        delivered = send_push(title="Reminder", body=r["title"], reminder_id=r["id"])
        if delivered:
            db.execute("UPDATE reminders SET sent = 1 WHERE id = ?", (r["id"],))
    db.commit()
    db.close()


def sync_calendar_job():
    from services import google_calendar
    from routes.calendar import sync_calendar_events_to_notes
    try:
        if google_calendar.is_connected():
            events = google_calendar.list_events()
            sync_calendar_events_to_notes(events)
    except Exception as e:
        print(f"Background Calendar Sync error: {e}")


def start_scheduler():
    scheduler.add_job(check_reminders, "interval", minutes=1, id="reminder_check")
    scheduler.add_job(sync_calendar_job, "interval", minutes=30, id="calendar_sync_job")
    scheduler.start()


def stop_scheduler():
    scheduler.shutdown()
