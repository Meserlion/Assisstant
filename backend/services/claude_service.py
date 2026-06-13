import json
import re
import anthropic
from config import settings


def _strip_json_fences(raw: str) -> str:
    """Remove markdown code fences from LLM responses before JSON parsing."""
    raw = raw.strip()
    raw = re.sub("^```[a-z]*\\n?", "", raw)
    raw = re.sub("\\n?```$", "", raw)
    return raw.strip()

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)


def tag_note(text: str, client_timezone: str = None, client_local_time: str = None) -> dict:
    """Returns a dict containing tags, summary, is_reminder, and reminder_details."""
    context = ""
    if client_local_time:
        context += f"User's local time: {client_local_time}\n"
    if client_timezone:
        context += f"User's local timezone: {client_timezone}\n"
        
    prompt = (
        "Analyze this note and return a JSON object with the following fields:\n"
        "- 'tags': array of 1-5 short lowercase tags.\n"
        "- 'summary': a one-sentence consolidated summary.\n"
        "- 'is_reminder': boolean. Set to true if the note indicates a reminder or scheduling request (e.g., starts with or contains 'remind me to', 'remember to', 'schedule a reminder', 'don't forget to', etc.).\n"
        "- 'reminder_details': if is_reminder is true, a JSON object containing 'title' (what to remind them of) and 'remind_at' (ISO 8601 UTC string of when to remind them). If no time is specified, default to 1 hour from now. If is_reminder is false, set reminder_details to null.\n\n"
        f"{context}"
        f"Note:\n{text}\n\n"
        "Return ONLY the valid JSON object, nothing else."
    )
    
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )
        raw = _strip_json_fences(response.content[0].text)
        data = json.loads(raw)
        return {
            "tags": data.get("tags", []),
            "summary": data.get("summary", ""),
            "is_reminder": data.get("is_reminder", False),
            "reminder_details": data.get("reminder_details")
        }
    except Exception as e:
        print(f"Error parsing tagged note: {e}")
        return {
            "tags": [],
            "summary": text[:50],
            "is_reminder": False,
            "reminder_details": None
        }


def rewrite_query(query: str, history: list[dict]) -> str:
    """Rewrite a follow-up query based on history to make it stand-alone for vector search."""
    if not history:
        return query
    
    # Format history for Claude
    formatted_history = ""
    for msg in history:
        role = "User" if msg["role"] == "user" else "Assistant"
        formatted_history += f"{role}: {msg['content']}\n"
        
    prompt = (
        "Given the following conversation history and a follow-up query, rewrite the follow-up query "
        "to be a search query that contains all necessary context for a vector search. "
        "Do not answer the query. Just output the rewritten query and nothing else.\n\n"
        f"History:\n{formatted_history}\n"
        f"Follow-up Query: {query}\n\n"
        "Rewritten Query:"
    )
    
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f"Error rewriting query: {e}")
        return query


QUERY_SYSTEM_PROMPT = (
    "You are a personal assistant with access to the user's notes and upcoming calendar schedule. "
    "Answer the query using only the provided notes and schedule. "
    "Be concise and direct. If the notes and schedule don't contain relevant info, say so."
)

# Cached system prompt block — reused across every RAG call in a session
_CACHED_SYSTEM = [{"type": "text", "text": QUERY_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]


def _build_query_messages(query: str, context_notes: list[dict], history: list[dict], schedule_context: str) -> list[dict]:
    notes_text = "\n\n".join(f"[{n['created_at']}] {n['raw_text']}" for n in context_notes)
    cleaned = []
    expected_role = "user"
    if history:
        for msg in history:
            if msg.get("role") == expected_role:
                cleaned.append({"role": msg["role"], "content": msg["content"]})
                expected_role = "assistant" if expected_role == "user" else "user"
    if expected_role == "assistant" and cleaned:
        cleaned.pop()
    # Split into a cacheable context block + a dynamic query block so repeated
    # note context (same search results across follow-up questions) hits cache.
    context_text = f"Notes:\n{notes_text}\n{schedule_context}".strip()
    user_content = []
    if context_text:
        user_content.append({"type": "text", "text": context_text, "cache_control": {"type": "ephemeral"}})
    user_content.append({"type": "text", "text": f"Query: {query}"})
    cleaned.append({"role": "user", "content": user_content})
    return cleaned


def answer_query(query: str, context_notes: list[dict], history: list[dict] = None, schedule_context: str = "") -> str:
    """Answer a search query using retrieved notes as context."""
    messages = _build_query_messages(query, context_notes, history or [], schedule_context)
    response = client.beta.prompt_caching.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=_CACHED_SYSTEM,
        messages=messages,
    )
    return response.content[0].text.strip()


def stream_answer_query(query: str, context_notes: list[dict], history: list[dict] = None, schedule_context: str = ""):
    """Yield text chunks for streaming the answer."""
    messages = _build_query_messages(query, context_notes, history or [], schedule_context)
    with client.beta.prompt_caching.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=_CACHED_SYSTEM,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            yield text


def rewrite_note(text: str, instruction: str) -> str:
    """Rewrite a note according to a user instruction (e.g. 'turn into a bullet list')."""
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": (
                f"Rewrite the following note according to this instruction: {instruction}\n\n"
                f"Note:\n{text}\n\n"
                "Return only the rewritten note, nothing else."
            )
        }]
    )
    return response.content[0].text.strip()


def synthesize_merged_note(notes: list[dict]) -> str:
    """Consolidate the raw texts of multiple notes into a single unified coherent note."""
    notes_texts = "\n---\n".join(
        f"Date: {n['created_at']}\nNote: {n['raw_text']}" for n in notes
    )
    prompt = (
        "You are an editor consolidating personal notes. Follow these rules strictly:\n\n"
        "1. PRESERVE DISTINCT TOPICS: If the notes cover clearly different subject areas "
        "(e.g. shopping list vs home tasks vs work tasks), keep them as separate sections "
        "with a short markdown header (e.g. '## Shopping List', '## Home Tasks'). "
        "Do NOT blend unrelated topics into one paragraph.\n"
        "2. REMOVE COMPLETED ITEMS: If a note mentions items that were already bought, "
        "done, or completed (phrases like 'already got', 'already bought', 'done', "
        "'finished', 'picked up'), omit those items from the output.\n"
        "3. DEDUPLICATE: Remove items that appear more than once across the notes.\n"
        "4. PRESERVE LIST FORMAT: If items are listed, keep them as bullet lines "
        "using '- item' format so they render as interactive checkboxes.\n"
        "5. TEMPORAL ORDER: Use dates to resolve conflicts — newer information takes precedence.\n\n"
        "Source Notes:\n" + notes_texts + "\n\n"
        "Consolidated Note:"
    )
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1536,
        messages=[{
            "role": "user",
            "content": prompt
        }]
    )
    return response.content[0].text.strip()


def cluster_notes(notes: list[dict]) -> dict:
    """Group notes by similarity and return a list of groups with consolidated summaries, and identify trash notes."""
    if not notes:
        return {"groups": [], "trash_note_ids": []}
    
    notes_data = []
    for n in notes:
        notes_data.append({
            "id": n["id"],
            "date": n["created_at"],
            "summary": n.get("summary", ""),
            "text": n["raw_text"]
        })
        
    prompt = (
        "You are an assistant that organizes notes. Analyze the input notes and perform two tasks:\n\n"
        "1. Group notes into logical semantic clusters/topics. Each cluster must consist of 2 or more notes that are highly related because they share the SAME SPECIFIC subject \u2014 the same project, event, trip, person, or concrete task. Do NOT group notes merely because they share a broad life-area or theme (e.g. do not lump 'shopping' together with 'chores' just because both are household/home-related; do not merge a shopping list with a maintenance to-do list). When in doubt, leave a note ungrouped. Also do not group notes that are organized under different section headers (e.g. '## Shopping List' vs '## Chores') unless they clearly concern the same specific subject. Notes that do not fit into any group should be left out of the groups.\n"
        "2. Identify any notes that are empty, contain only transcription errors/artifacts (like 'Thank you for watching', 'you', 'thank you' with no context), or are completely nonsensical (meaningless speech fragments, repetitive syllables, or gibberish that lacks any useful information or context). These notes should be marked as trash.\n\n"
        "Return a JSON object containing two keys:\n"
        "- 'groups': an array of objects. Each group object must have:\n"
        "  - 'topic': a short descriptive title for the group.\n"
        "  - 'summary': a one-sentence consolidated summary of what these notes are collectively about.\n"
        "  - 'note_ids': an array of the note IDs that belong to this group.\n"
        "- 'trash_note_ids': an array of note IDs that are empty or nonsensical and should be deleted.\n\n"
        "Input notes:\n" + json.dumps(notes_data, indent=2) + "\n\n"
        "Return ONLY the valid JSON object, nothing else."
    )
    
    # Cache the full prompt (instructions + notes JSON). On repeat Merge tab visits
    # where notes haven't changed, the entire call is served from cache.
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [{"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}]
        }]
    )

    raw = _strip_json_fences(response.content[0].text)
    try:
        data = json.loads(raw)
        return {
            "groups": data.get("groups", []),
            "trash_note_ids": data.get("trash_note_ids", [])
        }
    except Exception as e:
        print(f"Error parsing clustered groups: {e}")
        return {"groups": [], "trash_note_ids": []}


def describe_image(image_bytes: bytes, mime_type: str) -> str:
    """Send an image to Claude Vision and return a descriptive text to save as a note."""
    import base64
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": b64,
                    },
                },
                {
                    "type": "text",
                    "text": (
                        "You are saving a personal note from a photo. "
                        "Identify what type of image this is and extract only the useful information in the most compact, practical format.\n\n"
                        "Rules by image type:\n"
                        "- Handwritten list (shopping, to-do, etc.): transcribe as a clean bullet list. Fix obvious spelling. No intro text.\n"
                        "- Product / price tag / receipt: item name + price. If multiple items, list them.\n"
                        "- Shop / restaurant / location: name of place, address if visible, any relevant detail (hours, phone). One line per piece of info.\n"
                        "- Menu: dish names and prices only. Skip descriptions unless key.\n"
                        "- Document / sign / poster: transcribe the key text, skip decorative filler.\n"
                        "- Real-world scene with no text: one concise sentence of what it is and where (if determinable).\n\n"
                        "Never start with 'This image shows', 'I can see', or any meta-commentary. "
                        "Output only the note content itself, as if the user typed it."
                    ),
                }
            ],
        }]
    )
    return response.content[0].text

def research_note(text: str) -> str:
    """Return 2-3 brief relevant facts or context about the topic in a note."""
    prompt = (
        "You are a concise research assistant. Read the following personal note and identify its main topic.\n"
        "Then provide 2-3 brief, useful facts or context about that topic that would genuinely enrich it.\n"
        "Rules:\n"
        "- Each fact must be concrete and informative, not generic.\n"
        "- Keep each fact to one short sentence.\n"
        "- Format as a simple bullet list using `- ` prefix.\n"
        "- Do NOT restate what the note already says.\n"
        "- If the note is a to-do list or reminder with no clear researchable topic, respond with exactly: NO_RESEARCH\n\n"
        f"Note:\n{text}\n\n"
        "Research:"
    )
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}]
    )
    result = response.content[0].text.strip()
    if result == "NO_RESEARCH":
        return ""
    return result
