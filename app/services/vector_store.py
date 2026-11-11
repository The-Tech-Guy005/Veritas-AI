from functools import lru_cache
from pathlib import Path
import chromadb
from sentence_transformers import SentenceTransformer
from app.config import settings

@lru_cache(maxsize=1)
def get_embedder():
    return SentenceTransformer(settings.embedding_model)

@lru_cache(maxsize=1)
def get_collection():
    client = chromadb.PersistentClient(path=str(Path(settings.data_dir) / "chroma"))
    return client.get_or_create_collection(name=settings.chroma_collection, metadata={"hnsw:space": "cosine"})

def add_chunks(document_id: str, filename: str, chunks: list[str]) -> int:
    if not chunks:
        return 0
    collection = get_collection()
    embeddings = get_embedder().encode(chunks, normalize_embeddings=True).tolist()
    ids = [f"{document_id}_{i}" for i in range(len(chunks))]
    metadatas = [{"document_id": document_id, "filename": filename, "chunk_id": str(i)} for i in range(len(chunks))]
    collection.upsert(ids=ids, documents=chunks, embeddings=embeddings, metadatas=metadatas)
    return len(chunks)

def search_chunks(query: str, top_k: int = 5) -> list[dict]:
    collection = get_collection()
    if collection.count() == 0:
        return []
    embedding = get_embedder().encode([query], normalize_embeddings=True).tolist()
    result = collection.query(query_embeddings=embedding, n_results=min(top_k, collection.count()), include=["documents", "metadatas", "distances"])
    items = []
    for doc, meta, distance in zip(result["documents"][0], result["metadatas"][0], result["distances"][0]):
        items.append({"text": doc, **meta, "relevance_score": round(1 - float(distance), 4)})
    return items

def list_documents() -> list[dict]:
    collection = get_collection()
    if collection.count() == 0:
        return []
    data = collection.get(include=["metadatas"])
    unique = {}
    for meta in data["metadatas"]:
        unique[meta["document_id"]] = {"document_id": meta["document_id"], "filename": meta["filename"]}
    return list(unique.values())
