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


def answer_query(query: str, context_notes: list[dict], history: list[dict] = None) -> str:
    """Answer a search query using retrieved notes as context."""
    notes_text = "\n\n".join(
        f"[{n['created_at']}] {n['raw_text']}" for n in context_notes
    )
    
    system_prompt = (
        "You are a personal assistant with access to the user's notes. "
        "Answer the query using only the provided notes. "
        "Be concise and direct. If the notes don't contain relevant info, say so."
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
        
    user_content = f"Query: {query}\n\nNotes:\n{notes_text}"
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


def cluster_notes(notes: list[dict]) -> list[dict]:
    """Group notes by similarity and return a list of groups with consolidated summaries."""
    if not notes or len(notes) < 2:
        return []
    
    notes_data = []
    for n in notes:
        notes_data.append({
            "id": n["id"],
            "date": n["created_at"],
            "summary": n.get("summary", ""),
            "text": n["raw_text"]
        })
        
    prompt = (
        "You are an assistant that organizes notes. Group these notes into logical semantic clusters/topics. "
        "Each cluster must consist of 2 or more notes that are highly related (e.g. talking about the same project, event, or topic). "
        "Notes that do not fit into any group should be ignored.\n\n"
        "Return a JSON object containing a single key 'groups', which is an array of objects. Each group object must have:\n"
        "- 'topic': a short descriptive title for the group.\n"
        "- 'summary': a one-sentence consolidated summary of what these notes are collectively about.\n"
        "- 'note_ids': an array of the note IDs that belong to this group.\n\n"
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
        return data.get("groups", [])
    except Exception as e:
        print(f"Error parsing clustered groups: {e}")
        return []


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

