"""Minimal API smoke tests for the Assistant backend.

These run in CI before the deploy job (see .github/workflows/deploy.yml). They are
intentionally lightweight: they exercise auth, input validation, and the DB schema
without touching Anthropic, Chroma, or Whisper at runtime.

Environment is configured *before* importing the app so pydantic-settings picks up a
throwaway SQLite file and dummy keys, and never reads real data.
"""

import os
import tempfile

_TMPDIR = tempfile.mkdtemp(prefix="assistant-tests-")
os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ["SQLITE_DB_PATH"] = os.path.join(_TMPDIR, "notes.db")
os.environ["CHROMA_DB_PATH"] = os.path.join(_TMPDIR, "chroma")

import pytest
from fastapi.testclient import TestClient

from config import settings
from database import get_db, init_db
from main import app

KEY_HEADER = {"X-API-Key": settings.api_key}


@pytest.fixture(scope="module", autouse=True)
def _prepared_db():
    # Build the schema against the throwaway SQLite file. TestClient is used
    # without a context manager below, so the app's lifespan (which would start
    # the reminder scheduler and calendar sync) never runs -- we set up the DB here.
    init_db()
    yield


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_missing_api_key_is_rejected(client):
    # A present-but-wrong key reaches verify_key and returns 401; a *missing*
    # X-API-Key header is rejected earlier by APIKeyHeader itself, which returns
    # 403 in the pinned FastAPI (0.115.5). Either way the request is unauthorized.
    resp = client.get("/notes/")
    assert resp.status_code in (401, 403)


def test_wrong_api_key_returns_401(client):
    resp = client.get("/notes/", headers={"X-API-Key": "definitely-wrong"})
    assert resp.status_code == 401


def test_list_notes_with_valid_key_returns_list(client):
    resp = client.get("/notes/", headers=KEY_HEADER)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_invalid_color_returns_400(client):
    resp = client.patch(
        "/notes/some-id/color",
        headers=KEY_HEADER,
        json={"color": "chartreuse"},
    )
    assert resp.status_code == 400


def test_audio_without_token_returns_401(client):
    resp = client.get("/notes/some-id/audio")
    assert resp.status_code == 401


def test_init_db_creates_feed_index():
    init_db()
    conn = get_db()
    try:
        indexes = {row["name"] for row in conn.execute("PRAGMA index_list(notes)")}
    finally:
        conn.close()
    assert "idx_notes_list" in indexes
