# CLAUDE.md

This file provides guidance for Claude Code (claude.ai/code) and other AI assistants when working in this repository.

## Build, Run, and Lint Commands

### Frontend (`/frontend`)
*   **Install dependencies**: `npm install`
*   **Start development server**: `npm run dev` (proxies `/api` to `http://localhost:8000`)
*   **Production build**: `npm run build` (outputs to `dist/`)
*   **Lint checks**: `npm run lint` (ESLint)

### Backend (`/backend`)
*   **Start server**: `python -m uvicorn main:app --host 127.0.0.1 --port 8000` (or inside virtual env `venv/bin/uvicorn`)
*   **Database**: SQLite (`./data/notes.db`) and Chroma Vector DB (`./data/chroma`)

## Project Architecture & Tech Stack

The **Assistant** is a decoupled Client-Server application:
1.  **Frontend**: React (Vite-based SPA), Web Push (`public/sw.js`), and a custom **dark glassmorphism** styling system (`App.css`).
2.  **Backend**: FastAPI (Python), SQLite (relational storage), and ChromaDB (vector indexing for semantic search).
3.  **AI Services**: Anthropic API (Claude-Haiku for parsing voice reminders, Claude-Sonnet for RAG note syntheses) and `faster-whisper` (speech-to-text notes capture).

## Recent Changes & Overhauls (June 2026)

1.  **Premium Visual Redesign**:
    *   Added Google Fonts (`Outfit` and `Plus Jakarta Sans`) to `index.html`.
    *   Replaced `App.css` with a high-fidelity glassmorphic dark theme (`#070913` canvas, `rgba(22, 28, 45, 0.45)` containers).
    *   Added dynamic animations (pulsing microphone borders on active record, hover note lifts, custom scrollbars).
2.  **Lint & Compilation Fixes**:
    *   Removed dead imports and an unused `fetch('/api/notes/query/voice')` request block in `CalendarTab.jsx`.
    *   Cleaned up unused functions in `QueryPanel.jsx`.
    *   Patched global service worker namespace rules in `sw.js` and React effect warnings in `App.jsx`.
    *   Verified clean builds and lint outputs (`npm run lint` now returns zero errors).
3.  **Note Consolidation & Clustering Feature**:
    *   Exposed `/notes/groups` (semantic clustering of notes using Claude-Haiku) and `/notes/merge-group` (unified note synthesis using Claude-Sonnet).
    *   Implemented `ConsolidateTab` in the frontend showing topics, consolidated summaries, and nested note cards.
    *   Added a "Consolidate" action which merges multiple related notes into a single unified note (deleting the source ones in SQLite and Chroma DB).
4.  **Sticky Bottom Record Actions**:
    *   Moved voice buttons into a fixed-position `.bottom-bar` matching the page layout width.
    *   Optimized spacing for mobile viewports using CSS environment variables (`safe-area-inset-bottom`) and pointer-events transparency.
5.  **Visual Calendar/Scheduler Dashboard**:
    *   Added `selected_date` context to backend time parser (`_parse_reminder`) to support date-anchored scheduling.
    *   Created dynamic monthly grid calendar in `CalendarTab.jsx` with color-coded dot highlights (Indigo for Google Events, Emerald for local reminders).
    *   Implemented day cell selection loading the day's schedule detail view, featuring quick text typing and a mini voice button container.
6.  **Semantic Calendar Events Sync**:
    *   Implemented background calendar sync (`sync_calendar_events_to_notes`) inside `calendar.py` that inserts/updates Google Calendar events as special notes with a `["calendar"]` tag.
    *   Vectorizes calendar events in Chroma DB to make them searchable in the RAG conversational Ask tab.
    *   Modified notes listing and consolidation endpoints in `notes.py` to exclude notes tagged with `calendar` from the main notes feed and clustering processes.
