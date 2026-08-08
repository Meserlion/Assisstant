import uuid
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth import verify_key
from config import settings
from database import get_db

router = APIRouter(prefix="/push", tags=["push"])


class PushSubscription(BaseModel):
    subscription: dict


@router.get("/vapid-public-key", dependencies=[Depends(verify_key)])
def get_vapid_key():
    return {"public_key": settings.vapid_public_key}


@router.post("/subscribe", dependencies=[Depends(verify_key)])
def subscribe(req: PushSubscription):
    sub_id = str(uuid.uuid4())
    db = get_db()
    db.execute(
        "INSERT INTO push_subscriptions (id, subscription_json, created_at) VALUES (?, ?, ?)",
        (sub_id, json.dumps(req.subscription), datetime.now(timezone.utc).isoformat()),
    )
    db.commit()
    db.close()
    return {"id": sub_id}


@router.delete("/unsubscribe", dependencies=[Depends(verify_key)])
def unsubscribe(req: PushSubscription):
    endpoint = req.subscription.get("endpoint", "")
    db = get_db()
    db.execute(
        "DELETE FROM push_subscriptions WHERE subscription_json LIKE ?",
        (f"%{endpoint}%",),
    )
    db.commit()
    db.close()
    return {"ok": True}
