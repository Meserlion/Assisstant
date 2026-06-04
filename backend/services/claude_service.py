import json
import anthropic
from config import settings

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)


def tag_note(text: str) -> tuple[list[str], str]:
    """Returns (tags, summary) for a note."""
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{
            "role": "user",
            "content": (
                "Analyse this note and return a JSON object with two fields: "
                "'tags' (array of 1-5 short lowercase tag strings) and "
                "'summary' (one sentence). Note:\n\n" + text
            )
        }]
    )
    raw = response.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    data = json.loads(raw)
    return data["tags"], data["summary"]


def answer_query(query: str, context_notes: list[dict]) -> str:
    """Answer a search query using retrieved notes as context."""
    notes_text = "\n\n".join(
        f"[{n['created_at']}] {n['raw_text']}" for n in context_notes
    )
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=(
            "You are a personal assistant with access to the user's notes. "
            "Answer the query using only the provided notes. "
            "Be concise and direct. If the notes don't contain relevant info, say so."
        ),
        messages=[{
            "role": "user",
            "content": f"Query: {query}\n\nNotes:\n{notes_text}"
        }]
    )
    return response.content[0].text.strip()
