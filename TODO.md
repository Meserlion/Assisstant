# Backlog

## Pending

### 1. Full-text search bar
Quick filter across raw note text, separate from the semantic Ask tab. Frontend only: filter notes by `raw_text.toLowerCase().includes(query)` as the user types. No backend change needed.

### 2. Note colors
Color-code cards beyond tags (red = urgent, green = done, etc.). Backend: add a `color` column to notes. Frontend: color swatch picker in EditNoteModal, colored left-border on NoteCard.

### 3. Note aging indicator
Subtle visual on cards not touched in 7+ days to surface forgotten notes. Frontend only: compare `note.created_at` to today, add a `.note-aged` CSS class with a muted border or opacity fade after 7 days.

### 4. Notebooks / collections
Group notes into separate spaces (Work, Personal, Ideas). Backend: add a `notebook` column; frontend: notebook selector in the header, filter notes by active notebook.

### 5. Daily digest push notification
Morning push at a configurable time summarising today's schedule + a recap of recent notes. Backend: add a scheduler job that calls Claude-Haiku to produce a digest and sends it via the existing push service.

### 6. Save Ask conversation as a note
One button to persist a useful chat thread to the notes list. Frontend: "Save chat" button in QueryPanel that POSTs the conversation as a single text note.

### 7. Add calendar event from Ask tab
"Schedule X on Thursday" creates a Google Calendar event via voice or text in the Ask tab. Backend: extend the RAG answer path to detect scheduling intent and call the existing `google_calendar.create_event`.

### 8. Weekly recap note
Auto-generated end-of-week summary note from the past 7 days of notes. Backend: scheduler job every Sunday that calls Claude-Haiku and inserts the result as a note tagged `["recap"]`.

### 9. Share note
Copy a note as plain text or open the native share sheet on mobile. Frontend only: `navigator.share()` with fallback to clipboard copy, triggered by a share icon on NoteCard.

### 10. Offline indicator
PWA already caches assets but there's no UI feedback when disconnected. Frontend: listen to `window.online/offline` events and show a small banner when offline.

## Shipped

- Code review of Gemini changes → fixed 8 bugs (destructive GET, VoiceButton stuck, RefreshError, missed reminders, KeyError, summary discard, code duplication)
- Merge tab: synthesize_merged_note switched from Sonnet → Haiku (cost)
- Tag filter on Notes tab (click tag to filter, banner with clear)
- Streaming responses in Ask tab (SSE endpoint + frontend chunk rendering)
- Prompt caching on cluster_notes and RAG answer calls
- Clear conversation button in Ask tab
- Markdown rendering in Ask tab (react-markdown)
- AI summary shortcuts in Ask tab ("Summarise my week", "What did I do today?")
- Undo last delete (5-second toast, deferred API delete)
- Note count badge on tags
- Swipe to delete on mobile (touchstart/touchend, red reveal zone)
- Bulk delete / select notes (checkboxes + toolbar button)
- Note pinning (backend column + sort, 📌 toggle, frontend reorder)
- Voice note playback (audio saved on capture, <audio> on NoteCard)
- Recurring reminders (daily/weekly recurrence column, scheduler re-inserts next occurrence)
- Export notes as markdown (Blob download, already shipped)
