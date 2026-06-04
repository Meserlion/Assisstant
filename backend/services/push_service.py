import json
from pywebpush import webpush, WebPushException
from config import settings
from database import get_db


def get_subscriptions() -> list[dict]:
    db = get_db()
    rows = db.execute("SELECT subscription_json FROM push_subscriptions").fetchall()
    db.close()
    return [json.loads(r["subscription_json"]) for r in rows]


def _get_private_key() -> str:
    key = settings.vapid_private_key
    return key.replace("\\n", "\n")


def send_push(title: str, body: str):
    subs = get_subscriptions()
    if not subs or not settings.vapid_private_key:
        return
    payload = json.dumps({"title": title, "body": body})
    for sub in subs:
        try:
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=_get_private_key(),
                vapid_claims={"sub": f"mailto:{settings.vapid_email}"},
            )
        except WebPushException:
            pass
