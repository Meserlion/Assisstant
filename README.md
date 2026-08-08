# Assistant

A personal voice-first note-taking and reminder app with AI-powered organisation, semantic search, and Google Calendar integration.

## Features

### Capture
- **Voice notes** — hold to record, release to transcribe and save (Whisper STT); tap for toggle mode
- **Voice playback** — replay the original audio recording on any voice note
- **Text notes** — type directly; voice-to-text input also available in the text bar
- **Photo notes** — capture an image; Claude Vision describes it and saves it as a text note
- **Auto-tagging & summaries** — every note is tagged and summarised by Claude Haiku on capture

### Organisation
- **Pin & archive** — pin important notes to the top; swipe right to archive, left to delete
- **Undo delete** — a 5-second toast lets you undo an accidental deletion
- **Bulk select & delete** — checkbox multi-select with a single-tap bulk delete
- **Merge / Consolidate** — AI clusters similar notes; merge them into one clean summary (works with archived notes too — merged result always surfaces in the active feed)
- **Split note** — cut one note into two at any point
- **AI rewrite** — give an instruction (e.g. "make this a bullet list") to rewrite a note with Claude
- **Export** — download all notes as a Markdown file

### Search & Ask
- **Semantic search (Ask tab)** — ask questions in natural language; answers are streamed and grounded in your notes via RAG (ChromaDB + Claude Sonnet)
- **Streaming responses** — answers appear word-by-word; Markdown is rendered

### Calendar & Reminders
- **Smart reminders** — say "remind me to X at 3pm tomorrow" and a calendar event + notification are created automatically
- **Recurring reminders** — daily / weekly recurrence supported
- **Calendar view** — monthly grid with colour-coded dots (indigo = Google events, emerald = local reminders); tap a day to view its schedule
- **Google Calendar sync** — two-way: reminders push to Google, and upcoming events are pulled into the Ask context
- **Push notifications** — Web Push delivered to any subscribed device (VAPID)

## Tech stack

| Layer | Tech |
|---|---|
| Frontend | React (Vite SPA), dark glassmorphism theme |
| Backend | FastAPI (Python), SQLite, ChromaDB |
| AI | Claude Haiku (tagging/parsing), Claude Sonnet (RAG answers), faster-whisper (STT) |
| Auth | Single shared API key (`X-API-Key` header / query param for audio) |
| Calendar | Google Calendar OAuth 2.0 |
| Push | Web Push (VAPID) |

## Quick start (local development)

### Prerequisites

- Python 3.11+
- Node 18+
- ffmpeg (for audio remuxing — fixes browser seeking on recorded WebM files)
- An [Anthropic API key](https://console.anthropic.com/)

### Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env — set API_KEY, ANTHROPIC_API_KEY, and optionally Google / VAPID keys

python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev     # dev server at http://localhost:5173, proxies /api → :8000
```

Open `http://localhost:5173`, enter your `API_KEY` when prompted, and start recording.

### Production build

```bash
cd frontend && npm run build    # outputs to dist/
# Serve dist/ statically alongside the FastAPI backend (see deploy.sh for nginx config)
```

## Production deployment (Hetzner / any VPS)

```bash
chmod +x deploy.sh
sudo ./deploy.sh
```

The script installs all dependencies, builds the frontend, creates a systemd service, configures nginx as a reverse proxy, and obtains an SSL certificate via Certbot. Edit `DOMAIN` and `EMAIL` at the top of `deploy.sh` before running.

After the script finishes:

```bash
nano /opt/assistant/backend/.env   # fill in API keys
systemctl restart assistant
```

## Environment variables (`.env`)

Copy `backend/.env.example` to `backend/.env` and fill in the values.

| Variable | Required | Description |
|---|---|---|
| `API_KEY` | ✓ | Shared secret for frontend ↔ backend auth. Generate with `openssl rand -hex 32`. |
| `ANTHROPIC_API_KEY` | ✓ | Anthropic API key from [console.anthropic.com](https://console.anthropic.com/) |
| `WHISPER_MODEL` | | `tiny`, `small`, or `medium`. Default: `small`. Larger = more accurate, slower. |
| `SQLITE_DB_PATH` | | Default: `./data/notes.db` |
| `CHROMA_DB_PATH` | | Default: `./data/chroma` |
| `GOOGLE_CLIENT_ID` | | Google OAuth client ID (Calendar sync) |
| `GOOGLE_CLIENT_SECRET` | | Google OAuth client secret |
| `GOOGLE_REDIRECT_URI` | | OAuth callback URL, e.g. `https://yourdomain.com/api/calendar/oauth/callback` |
| `VAPID_PRIVATE_KEY` | | VAPID private key (push notifications) |
| `VAPID_PUBLIC_KEY` | | VAPID public key |
| `VAPID_EMAIL` | | Contact email for VAPID |

### Generating VAPID keys (for push notifications)

```bash
pip install pywebpush
python -c "from py_vapid import Vapid; v = Vapid(); v.generate_keys(); print('Private:', v.private_pem().decode()); print('Public:', v.public_key.public_bytes(__import__('cryptography.hazmat.primitives.serialization', fromlist=['Encoding','PublicFormat']).Encoding.X962, __import__('cryptography.hazmat.primitives.serialization', fromlist=['Encoding','PublicFormat']).PublicFormat.UncompressedPoint).hex())"
```

Or more simply — use the [`web-push` npm package](https://www.npmjs.com/package/web-push):

```bash
npx web-push generate-vapid-keys
```

Paste the output into `VAPID_PRIVATE_KEY` and `VAPID_PUBLIC_KEY`.

## Google Calendar integration

1. Create a Google Cloud project and enable the Calendar API.
2. Add `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REDIRECT_URI` to `.env`.
3. Open **Settings → Connect Google Calendar** in the app and complete the OAuth flow.

Once connected, reminders sync to Google Calendar, and your upcoming events appear on the calendar grid and are searchable via Ask.

## Data storage

All data lives in `backend/data/`:

| Path | Contents |
|---|---|
| `notes.db` | SQLite database (notes, reminders, push subscriptions) |
| `chroma/` | ChromaDB vector index |
| `audio/` | UUID-named audio files for voice notes |

## Development notes

- `npm run lint` in `frontend/` should return zero errors.
- The dev server proxies `/api/*` → `http://localhost:8000` via Vite config.
- Audio playback uses `/api/notes/{id}/audio?key=<api_key>` — query-param auth so the browser's native `<audio>` element can authenticate without custom headers.
- Calendar events sync as notes tagged `["calendar"]`, excluded from the main feed and consolidation clustering.
- The recorder auto-detects the best supported MIME type (`audio/webm;codecs=opus` → `audio/mp4` → fallback), so playback works across Chrome, Firefox, and Safari.

## Troubleshooting

| Problem | Fix |
|---|---|
| Audio notes won't play | Ensure the backend `data/audio/` directory is writable. On Safari/iOS, audio is recorded as `audio/mp4`; the app handles this automatically. In a production PWA install, the service worker uses `NetworkOnly` for all `/api/` requests so audio range-request streaming is not interfered with. |
| Transcription is slow | Switch `WHISPER_MODEL=tiny` in `.env` and restart the backend. |
| Google Calendar not syncing | Check that `GOOGLE_REDIRECT_URI` in `.env` exactly matches the URI in your Google Cloud OAuth app settings. |
| Push notifications not arriving | Regenerate VAPID keys, update `.env`, and re-subscribe in the app (Settings → Push Notifications). |
| `401 Unauthorized` on all requests | The API key entered in the app must match `API_KEY` in the backend `.env`. Clear site data and re-enter the key. |
| Stale PWA serving old files | Hard-reload (`Ctrl+Shift+R` / `Cmd+Shift+R`) or clear the browser cache. The service worker updates automatically on next visit. |
