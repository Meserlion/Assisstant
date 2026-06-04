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
        send_push(title="Reminder", body=r["title"])
        db.execute("UPDATE reminders SET sent = 1 WHERE id = ?", (r["id"],))
    db.commit()
    db.close()


def start_scheduler():
    scheduler.add_job(check_reminders, "interval", minutes=1, id="reminder_check")
    scheduler.start()


def stop_scheduler():
    scheduler.shutdown()
