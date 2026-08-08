import hashlib
import hmac
import secrets
import time

from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader

from config import settings

api_key_header = APIKeyHeader(name="X-API-Key")

# How long a generated audio URL stays playable. The notes feed is refetched
# far more often than this, so tokens are refreshed well before they lapse.
AUDIO_TOKEN_TTL_SECONDS = 3600


def key_is_valid(candidate: str | None) -> bool:
    """Constant-time comparison so a wrong key can't be narrowed down by timing."""
    return secrets.compare_digest(candidate or "", settings.api_key)


def verify_key(key: str = Depends(api_key_header)):
    if not key_is_valid(key):
        raise HTTPException(status_code=401, detail="Invalid API key")


def _audio_signature(note_id: str, expires: int) -> str:
    message = f"{note_id}:{expires}".encode()
    return hmac.new(settings.api_key.encode(), message, hashlib.sha256).hexdigest()


def make_audio_token(note_id: str) -> str:
    """Mint a short-lived, single-note token.

    `<audio src>` cannot send custom headers, so the URL has to carry its own
    credential. Putting the master API key there leaks it into nginx access logs,
    browser history and Referer headers; this token instead grants one note's
    audio for one hour and cannot be replayed against any other endpoint.
    """
    expires = int(time.time()) + AUDIO_TOKEN_TTL_SECONDS
    return f"{expires}.{_audio_signature(note_id, expires)}"


def audio_token_is_valid(note_id: str, token: str | None) -> bool:
    if not token or "." not in token:
        return False
    expires_raw, _, signature = token.partition(".")
    try:
        expires = int(expires_raw)
    except ValueError:
        return False
    if expires < time.time():
        return False
    return secrets.compare_digest(signature, _audio_signature(note_id, expires))
