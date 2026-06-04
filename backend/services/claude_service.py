import json
import anthropic
from config import settings

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
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
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


def answer_query(query: str, context_notes: list[dict], history: list[dict] = None, schedule_context: str = "") -> str:
    """Answer a search query using retrieved notes as context."""
    notes_text = "\n\n".join(
        f"[{n['created_at']}] {n['raw_text']}" for n in context_notes
    )
    
    system_prompt = (
        "You are a personal assistant with access to the user's notes and upcoming calendar schedule. "
        "Answer the query using only the provided notes and schedule. "
        "Be concise and direct. If the notes and schedule don't contain relevant info, say so."
    )
    
    cleaned_messages = []
    expected_role = "user"
    if history:
        for msg in history:
            if msg.get("role") == expected_role:
                cleaned_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
                expected_role = "assistant" if expected_role == "user" else "user"
                
    if expected_role == "assistant" and cleaned_messages:
        cleaned_messages.pop()
        
    user_content = f"Query: {query}\n\nNotes:\n{notes_text}\n{schedule_context}"
    cleaned_messages.append({
        "role": "user",
        "content": user_content
    })
    
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=system_prompt,
        messages=cleaned_messages
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
        "1. Group notes into logical semantic clusters/topics. Each cluster must consist of 2 or more notes that are highly related (e.g. talking about the same project, event, or topic). Notes that do not fit into any group should be left out of the groups.\n"
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
    
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": prompt
        }]
    )
    
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        data = json.loads(raw)
        return {
            "groups": data.get("groups", []),
            "trash_note_ids": data.get("trash_note_ids", [])
        }
    except Exception as e:
        print(f"Error parsing clustered groups: {e}")
        return {"groups": [], "trash_note_ids": []}


def synthesize_merged_note(notes: list[dict]) -> str:
    """Consolidate the raw texts of multiple notes into a single unified coherent note."""
    notes_texts = "\n---\n".join(
        f"Date: {n['created_at']}\nNote: {n['raw_text']}" for n in notes
    )
    prompt = (
        "You are an editor. Consolidate the following notes into a single, unified, coherent note. "
        "Combine duplicate information, resolve temporal order based on dates, and write a single "
        "flowable, well-structured text. Keep all important facts, detail, and tone.\n\n"
        "Source Notes:\n" + notes_texts + "\n\n"
        "Unified Note:"
    )
    
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1536,
        messages=[{
            "role": "user",
            "content": prompt
        }]
    )
    return response.content[0].text.strip()

