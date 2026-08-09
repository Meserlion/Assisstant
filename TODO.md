# Backlog

## How to use this file

Tasks in **Tech Debt** are written to be implemented directly. Each one gives you the exact
file, the exact text to find, and the exact text to replace it with. Do not redesign them.

### Picking a task

Pick the **lowest-numbered task whose checkbox is still unticked** and whose `BLOCKED BY` line
(if it has one) names only tasks that are already ticked. If the next task is blocked, skip it and
take the next eligible one.

> **Never start a task whose `BLOCKED BY` prerequisite is unticked**, and never split a task that
> says its changes must ship together. TD2 will take the live Ask tab down if it is deployed without
> TD1, or if its two file changes are split across separate deploys. The checkbox is the only source
> of truth for whether a prerequisite is done — do not infer it from the code.

**When you finish a task, tick its checkbox in this file in the same commit as the code change.**
A task is not done until its box is ticked on `main`.

Rules:
- **Start from an up-to-date checkout.** Run `git fetch origin main && git status` first. If the
  branch is behind, pull before editing. Committing from a stale checkout silently reverts other
  people's work — this has already happened on this repo.
- **Stage only the files you actually edited** (`git add <path>`), never `git add -A`. A blanket add
  from a stale or dirty tree is how truncated files and duplicate commits have reached `main` before.
- **Re-read each file immediately before editing it, and write it back whole.** Three files
  (`backend/database.py`, `README.md`, and a CSS rule fixed in `697f4a7`) have been pushed to `main`
  truncated mid-line. After writing any file, confirm it still ends with a complete line.
- One task per commit. Commit message format: `fix: <task title> (TD<n>)`.
- After any change under `frontend/`, run `npm run lint` in `frontend/` and confirm zero errors, then
  run `npm run build && npm run test:smoke`. The smoke tests gate the deploy. If they fail and you did
  not intend to change the app's structure, your change is wrong — fix the code. If the task genuinely
  changes the shell, update `frontend/tests/smoke.spec.js` in the same commit. Never weaken an
  assertion to get green.
- After pushing to `main`, confirm the "Deploy to Hetzner" Actions run shows **Success** before starting the next task.
- Line numbers are accurate as of commit `ce7b976`. If a line has moved, search for the quoted
  text instead — the quoted text is authoritative, the line number is only a hint.
- If a task's "find" text does not appear in the file, stop and report it. Do not guess a substitute.

---

## Tech Debt

### [x] TD1. Install backend dependencies during deploy

**File:** `.github/workflows/deploy.yml` (~line 33)

**Why:** The deploy script builds the frontend but never installs Python packages. Any new entry in
`backend/requirements.txt` is silently ignored, so the service restarts with stale dependencies and
crashes on import. This blocks TD2.

**Find:**
```yaml
            cd /opt/assistant
            git pull
            cd frontend
```

**Replace with:**
```yaml
            cd /opt/assistant
            git pull
            pip install -r backend/requirements.txt
            cd frontend
```

**Verify:** Push and confirm the Actions run succeeds and `curl https://mcgreeff-assistant.duckdns.org/api/health` returns 200.

**Note:** If the backend runs inside a virtualenv on the server, use that venv's pip instead
(e.g. `/opt/assistant/backend/venv/bin/pip install -r backend/requirements.txt`). Check with
`ssh root@91.98.46.215 'systemctl cat assistant | grep ExecStart'` to see which interpreter is used.

---

### [x] TD2. Upgrade the Anthropic SDK and drop `beta.prompt_caching`

**Files:** `backend/requirements.txt` (line 5) and `backend/services/claude_service.py` (lines 133, 145)

**BLOCKED BY: TD1.**

**Why:** `anthropic==0.40.0` is very old. `client.beta.prompt_caching` was removed from the SDK when
prompt caching went GA; the current API is plain `client.messages`.

**These two changes MUST ship in the same commit and the same deploy.** They are not independent:
the old SDK is the only reason the `beta.prompt_caching` calls work today, and the new SDK is the
only thing that makes `client.messages` with `cache_control` current. Deploying either one alone
takes the Ask tab down until the other lands.

**Change 1 — `backend/requirements.txt`, find:**
```
anthropic==0.40.0
```
**Replace with:**
```
anthropic==0.116.0
```

**Change 2 — `backend/services/claude_service.py`, find:**
```python
    response = client.beta.prompt_caching.messages.create(
```
**Replace with:**
```python
    response = client.messages.create(
```

**Change 3 — `backend/services/claude_service.py`, find:**
```python
    with client.beta.prompt_caching.messages.stream(
```
**Replace with:**
```python
    with client.messages.stream(
```

Change nothing else. The `system=_CACHED_SYSTEM` argument and every `cache_control` block stay
exactly as they are — both are supported on `client.messages`.

**Before committing**, confirm no occurrences remain:
```bash
grep -n "beta.prompt_caching" backend/services/claude_service.py   # must print nothing
grep -n "anthropic==" backend/requirements.txt                     # must show 0.116.0
```

**Verify:** After deploy, open the Ask tab and send one question; confirm it answers and that
streaming renders progressively. If it errors, check
`ssh root@91.98.46.215 'journalctl -u assistant -n 50'` and report the traceback rather than
reverting blindly.

---

### [x] TD3. Update model IDs

**File:** `backend/services/claude_service.py`

**Why:** `claude-sonnet-4-6` is the previous-generation Sonnet; `claude-sonnet-5` is current and
better at the RAG answering these calls do. The dated Haiku ID works but the undated alias is
preferred because it does not go stale.

**Change 1:** Replace **all** occurrences of `model="claude-sonnet-4-6"` with `model="claude-sonnet-5"` (2 occurrences, lines 134 and 146).

**Change 2:** Replace **all** occurrences of `model="claude-haiku-4-5-20251001"` with `model="claude-haiku-4-5"` (7 occurrences).

Do not change any other part of these calls.

**Verify:** Ask tab answers a question; capture one voice note and confirm it still gets tags and a summary.

---

### [x] TD4. Enable SQLite WAL mode and a busy timeout

**File:** `backend/database.py` (lines 6-10)

**Why:** Three background threads (`_background_index_note`, `_background_calendar_sync`,
`_background_remux` in `backend/routes/notes.py`) write to SQLite while request handlers are also
writing. Without WAL and a busy timeout this produces `database is locked` errors under concurrency.
`os.makedirs` also runs on every single call, which is a wasted syscall per query.

**Find:**
```python
def get_db():
    os.makedirs(os.path.dirname(settings.sqlite_db_path), exist_ok=True)
    conn = sqlite3.connect(settings.sqlite_db_path)
    conn.row_factory = sqlite3.Row
    return conn
```

**Replace with:**
```python
_db_dir_ready = False


def get_db():
    global _db_dir_ready
    if not _db_dir_ready:
        os.makedirs(os.path.dirname(settings.sqlite_db_path), exist_ok=True)
        _db_dir_ready = True
    conn = sqlite3.connect(settings.sqlite_db_path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    # WAL lets readers and writers run concurrently; busy_timeout makes a blocked
    # writer wait instead of raising "database is locked" immediately.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn
```

**Verify:** Restart the backend, capture a voice note, and confirm it appears in the list with tags.

---

### [x] TD5. Stop blocking the event loop during transcription

**File:** `backend/routes/notes.py` (lines 460 and 575)

**Why:** Both call sites run Whisper synchronously inside an `async def`, which freezes the entire
server for the duration of the transcription — no other request can be served. `capture_note`
already does this correctly on line 163 using `asyncio.to_thread`. `asyncio` is already imported.

**Change 1 — in `transcribe_audio` (~line 460), find:**
```python
        text = whisper_service.transcribe(tmp_path)
    finally:
        os.unlink(tmp_path)

    return {"text": text}
```
**Replace with:**
```python
        text = await asyncio.to_thread(whisper_service.transcribe, tmp_path)
    finally:
        os.unlink(tmp_path)

    return {"text": text}
```

**Change 2 — in `query_notes_voice` (~line 575), find:**
```python
        text = whisper_service.transcribe(tmp_path)
    finally:
        os.unlink(tmp_path)

    try:
        history_list = json.loads(history)
```
**Replace with:**
```python
        text = await asyncio.to_thread(whisper_service.transcribe, tmp_path)
    finally:
        os.unlink(tmp_path)

    try:
        history_list = json.loads(history)
```

**Verify:** Record a voice query in the Ask tab and confirm it transcribes and answers.

---

### [x] TD6. Don't drop notes from search when re-indexing fails

**File:** `backend/routes/notes.py` (lines 390 and 427)

**Why:** Both spots delete the note's vector and then add the new one. If the add throws, the note is
gone from semantic search permanently and nothing is logged. `_background_index_note` (line ~74)
already handles this correctly — copy its approach.

**There are two occurrences of this pattern.** Both look like:
```python
    chroma_service.delete_note(note_id)
    chroma_service.add_note(note_id, <TEXT_VAR>, {"created_at": row["created_at"], "tags": json.dumps(tags), "summary": summary})
```
where `<TEXT_VAR>` is `req.text` at line ~390 and `new_text` at line ~427.

**For each occurrence, wrap it:**
```python
    try:
        chroma_service.delete_note(note_id)
        chroma_service.add_note(note_id, <TEXT_VAR>, {"created_at": row["created_at"], "tags": json.dumps(tags), "summary": summary})
    except Exception as e:
        print(f"CHROMA_SYNC_FAILURE note_id={note_id} error={e} — note saved but search index is stale")
```
Keep `<TEXT_VAR>` exactly as it already is in each spot. Do not swap them.

**Verify:** Edit an existing note, save, then find it via the Ask tab.

---

### [x] TD7. Refresh the note list with the correct archived filter

**File:** `frontend/src/App.jsx` (lines 60 and 75)

**Why:** Both calls omit the argument, so `fetchNotes` falls back to `archived = false`. Capturing a
voice note or a photo while viewing archived notes silently swaps the list to active notes without
the toggle changing.

**Find (2 occurrences, in `handleStop` and `handleImageSelect`):**
```javascript
      await fetchNotes()
```
**Replace both with:**
```javascript
      await fetchNotes(showArchived)
```

`showArchived` is already in scope in both functions (declared line 32).

**Verify:** Run `npm run lint` (zero errors). Switch to archived view, capture a note, and confirm the view stays on archived.

---

### [x] TD8. Replace the deprecated FastAPI startup hooks

**File:** `backend/main.py` (lines 21 and 27)

**Why:** `@app.on_event` is deprecated and will be removed in a future FastAPI release.

**Find:**
```python
app = FastAPI(title="Assistant API")
```
**Replace with:**
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Assistant API", lifespan=lifespan)
```

**Then find and delete entirely:**
```python
@app.on_event("startup")
def startup():
    init_db()
    start_scheduler()


@app.on_event("shutdown")
def shutdown():
    stop_scheduler()
```

**Then add this import at the top of the file, above `from fastapi import FastAPI`:**
```python
from contextlib import asynccontextmanager
```

**Verify:** Backend starts without warnings; `/api/health` returns 200; a reminder still fires.

---

### [x] TD9. Remove the dead "research note" feature

**Why:** The UI button was removed in commit `d161fe8`, but the endpoint and client function are
still shipped. Dead code that still costs an Anthropic API call if anyone hits the route.

**Delete these three things:**
1. `backend/routes/notes.py` — the whole `research_note` route function starting at the line
   `@router.post("/{note_id}/research", response_model=NoteResponse, dependencies=[Depends(verify_key)])`
   through the end of that function (ends with the closing `)` of its final `return NoteResponse(...)`).
2. `backend/services/claude_service.py` — the whole `def research_note(text: str) -> str:` function.
3. `frontend/src/api/client.js` — the whole `export async function researchNote(id) { ... }` function.

**Before deleting**, run `grep -rn "researchNote\|research_note" frontend/src backend` and confirm no
other file calls them. If something does, stop and report it.

**Verify:** `npm run lint` passes; the app loads and notes render.

---

### [x] TD10. De-duplicate the two RAG query handlers

**File:** `backend/routes/notes.py` (`query_notes` ~line 467 and `query_notes_stream` ~line 517)

**Why:** Roughly 45 lines are copy-pasted between the two, so every RAG change has to be made twice
and they can drift apart.

**What to do:** Extract the shared part — rewriting the search query, running the Chroma search,
loading the calendar schedule context, and building the `sources` list — into one helper:

```python
def _build_query_context(req: QueryRequest) -> tuple[list[NoteResponse], str]:
    """Returns (sources, schedule_context) shared by the plain and streaming query routes."""
```

Then have both routes call it. `query_notes` uses the result for `claude_service.answer_query`;
`query_notes_stream` uses it for `claude_service.stream_answer_query`.

**Do not change any behaviour** — same search, same 7-day calendar window, same response shape.

**Verify:** Ask a question in both streaming and non-streaming mode and confirm identical sources.

---

### [ ] TD11. Add a minimal backend test suite and run it in CI

**Why:** There are currently zero tests, and `main` receives automated commits. Two of those commits
shipped truncated files (`backend/database.py`, `README.md`) that no check caught.

**Create `backend/tests/test_api.py`** using `fastapi.testclient.TestClient`, covering:
- A request with no `X-API-Key` returns 401.
- A request with a wrong `X-API-Key` returns 401.
- `GET /notes/` with the correct key returns 200 and a list.
- `PATCH /notes/{id}/color` with `{"color": "chartreuse"}` returns 400 (not in `ALLOWED_COLORS`).
- `GET /notes/{id}/audio` with no `t` parameter returns 401.
- `init_db()` runs and afterwards `PRAGMA index_list(notes)` includes `idx_notes_list`
  (this is the check that would have caught the truncation).

Point the tests at a temporary SQLite file via the `SQLITE_DB_PATH` env var so they never touch real data.

**Add `pytest` and `httpx` to `backend/requirements.txt`.**

**Add a job to `.github/workflows/deploy.yml` that runs before `deploy`**, and add `test` to the
`deploy` job's `needs:` list so a failing test blocks the deploy:

```yaml
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.13'
      - name: Install and test
        working-directory: backend
        run: |
          pip install -r requirements.txt
          pytest -q
```

**Verify:** The Actions run shows the test job passing.

---

### [ ] TD12. Ignore local Claude settings

**File:** `.gitignore`

**Why:** `.claude/settings.local.json` is machine-specific and should not be committed.

**Append:**
```
# Claude Code local settings
.claude/settings.local.json
```

**Verify:** `git status` no longer lists that file.

---

## Feature Backlog

### [ ] F1. Notebooks / collections
Group notes into separate spaces (Work, Personal, Ideas). Backend: add a `notebook` column; frontend: notebook selector in the header, filter notes by active notebook.

### [ ] F2. Daily digest push notification
Morning push at a configurable time summarising today's schedule + a recap of recent notes. Backend: add a scheduler job that calls Claude-Haiku to produce a digest and sends it via the existing push service.

### [ ] F3. Save Ask conversation as a note
One button to persist a useful chat thread to the notes list. Frontend: "Save chat" button in QueryPanel that POSTs the conversation as a single text note.

### [ ] F4. Add calendar event from Ask tab
"Schedule X on Thursday" creates a Google Calendar event via voice or text in the Ask tab. Backend: extend the RAG answer path to detect scheduling intent and call the existing `google_calendar.create_event`.

### [ ] F5. Weekly recap note
Auto-generated end-of-week summary note from the past 7 days of notes. Backend: scheduler job every Sunday that calls Claude-Haiku and inserts the result as a note tagged `["recap"]`.

### [ ] F6. Share note
Copy a note as plain text or open the native share sheet on mobile. Frontend only: `navigator.share()` with fallback to clipboard copy, triggered by a share icon on NoteCard.

### [ ] F7. Offline indicator
PWA already caches assets but there's no UI feedback when disconnected. Frontend: listen to `window.online/offline` events and show a small banner when offline.

### [ ] F8. Split `App.css` and `routes/notes.py`
`App.css` is ~2300 lines and `backend/routes/notes.py` is ~750. Split the CSS by component and move the clustering/merge endpoints out of `notes.py` into `routes/consolidate.py`. Cosmetic only — no behaviour change.

---

## Shipped

- Security: removed the API key from audio URLs (per-note HMAC token, 1h expiry), restricted CORS to configured origins, constant-time key comparison, four copies of `verify_key` merged into `backend/auth.py`
- Fixed `backend/database.py` truncated mid-line — restored the feed indexes plus `conn.commit()` / `conn.close()`
- Fixed `README.md` truncated mid-line — restored the env-var table and Troubleshooting section
- MCP server exposing notes to Claude Desktop (`assistant_mcp.py`, `MCP_SETUP.md`)
- `MediaRecorder` MIME-type detection so iOS Safari voice capture works
- Sanitised `backend/.env.example` (no real deployment URL or personal email)
- Full-text search on the Notes tab
- Note colour coding with swatch picker
- Note aging / stale indicator
- Checklist rendering and progress badge on note cards
- Swipe right to archive notes
- Note consolidation and clustering (Merge tab)
- Code review of Gemini changes → fixed 8 bugs (destructive GET, VoiceButton stuck, RefreshError, missed reminders, KeyError, summary discard, code duplication)
- Merge tab: `synthesize_merged_note` switched from Sonnet → Haiku (cost)
- Tag filter on Notes tab (click tag to filter, banner with clear)
- Streaming responses in Ask tab (SSE endpoint + frontend chunk rendering)
- Prompt caching on `cluster_notes` and RAG answer calls
- Clear conversation button in Ask tab
- Markdown rendering in Ask tab (react-markdown)
- AI summary shortcuts in Ask tab ("Summarise my week", "What did I do today?")
- Undo last delete (5-second toast, deferred API delete)
- Note count badge on tags
- Swipe to delete on mobile (touchstart/touchend, red reveal zone)
- Bulk delete / select notes (checkboxes + toolbar button)
- Note pinning (backend column + sort, 📌 toggle, frontend reorder)
- Voice note playback (audio saved on capture, `<audio>` on NoteCard)
- Recurring reminders (daily/weekly recurrence column, scheduler re-inserts next occurrence)
- Export notes as markdown (Blob download)
