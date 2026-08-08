# Assistant MCP — Setup Guide

This MCP server lets Claude desktop (Cowork / Claude Code) create, read, edit, delete, and search your personal Assistant notes directly from any conversation.

---

## 1. Install the dependency

The server needs the MCP Python SDK and `httpx`. Run this once in the repo root (or your venv):

```bash
pip install "mcp[cli]" httpx
```

---

## 2. Find your API key

Open `D:\Programs\Assistant\backend\.env` and copy the value of `api_key`:

```
api_key=YOUR_KEY_HERE
```

---

## 3. Add the server to Claude's MCP config

Open (or create) the file:

```
%APPDATA%\Claude\claude_desktop_config.json
```

Add an entry under `"mcpServers"`:

```json
{
  "mcpServers": {
    "assistant": {
      "command": "python",
      "args": ["D:\\Programs\\Assistant\\assistant_mcp.py"],
      "env": {
        "ASSISTANT_API_KEY": "YOUR_KEY_HERE",
        "ASSISTANT_BASE_URL": "http://localhost:8000"
      }
    }
  }
}
```

Replace `YOUR_KEY_HERE` with the key you found in step 2.

> If Python isn't on your PATH, use the full path, e.g. `"C:\\Python311\\python.exe"`.

---

## 4. Restart Claude desktop

Close and reopen the Claude desktop app. The MCP server starts automatically alongside it.

---

## Available tools

| Tool | What it does |
|---|---|
| `assistant_list_notes` | List notes (with pagination, archived toggle) |
| `assistant_get_note` | Fetch a single note by ID |
| `assistant_create_note` | Create a new note (auto-tagged + summarised) |
| `assistant_update_note` | Replace a note's text (re-tags automatically) |
| `assistant_delete_note` | Permanently delete a note ⚠️ |
| `assistant_search_notes` | Semantic RAG search with AI-synthesised answer |
| `assistant_pin_note` | Pin or unpin a note |
| `assistant_archive_note` | Archive or restore a note |

---

## Example prompts once connected

- *"Show me my last 10 notes"*
- *"Create a note: buy milk, eggs, and bread"*
- *"Edit my note about the project deadline"*
- *"Delete the note about the old meeting"*
- *"What have I written about Python recently?"*
- *"Pin the shopping list note"*

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Error: Invalid API key` | Check `ASSISTANT_API_KEY` matches `api_key` in backend `.env` |
| `Error: Could not connect` | Make sure the backend is running (`python -m uvicorn main:app ...`) |
| Server not appearing in Claude | Restart the app; check JSON syntax in `claude_desktop_config.json` |
| `ModuleNotFoundError: mcp` | Run `pip install "mcp[cli]" httpx` |
