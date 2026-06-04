import os
import chromadb
from chromadb.utils import embedding_functions
from config import settings

_client = None
_collection = None


def get_collection():
    global _client, _collection
    if _collection is None:
        os.makedirs(settings.chroma_db_path, exist_ok=True)
        _client = chromadb.PersistentClient(path=settings.chroma_db_path)
        ef = embedding_functions.DefaultEmbeddingFunction()
        _collection = _client.get_or_create_collection(
            name="notes",
            embedding_function=ef,
        )
    return _collection


def add_note(note_id: str, text: str, metadata: dict):
    get_collection().add(
        ids=[note_id],
        documents=[text],
        metadatas=[metadata],
    )


def search_notes(query: str, n_results: int = 5) -> list[dict]:
    results = get_collection().query(
        query_texts=[query],
        n_results=n_results,
    )
    notes = []
    for i, doc in enumerate(results["documents"][0]):
        notes.append({
            "id": results["ids"][0][i],
            "raw_text": doc,
            **results["metadatas"][0][i],
        })
    return notes


def delete_note(note_id: str):
    get_collection().delete(ids=[note_id])
