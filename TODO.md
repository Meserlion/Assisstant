# Backlog

## Pending

*(backlog clear)*

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
