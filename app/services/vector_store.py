from pathlib import Path
import chromadb
from app.config import settings

def get_collection():
    client = chromadb.PersistentClient(path=str(Path(settings.data_dir) / "chroma"))
    return client.get_or_create_collection(
        name=settings.chroma_collection,
        metadata={"hnsw:space": "cosine"}
    )

def add_chunks(document_id, filename, chunks):
    if not chunks:
        return 0
    collection = get_collection()
    ids = [document_id + "_" + str(i) for i in range(len(chunks))]
    metadatas = [
        {"document_id": document_id, "filename": filename, "chunk_id": str(i)}
        for i in range(len(chunks))
    ]
    # Chroma's default embedding function generates and stores embeddings automatically.
    collection.upsert(ids=ids, documents=chunks, metadatas=metadatas)
    return len(chunks)

def search_chunks(query, top_k=5):
    collection = get_collection()
    count = collection.count()
    if count == 0:
        return []
    result = collection.query(
        query_texts=[query],
        n_results=min(top_k, count),
        include=["documents", "metadatas", "distances"]
    )
    output = []
    docs = result.get("documents", [[]])[0]
    metas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    for text, meta, distance in zip(docs, metas, distances):
        output.append({
            "text": text,
            "document_id": meta.get("document_id", ""),
            "filename": meta.get("filename", ""),
            "chunk_id": meta.get("chunk_id", ""),
            "relevance_score": round(max(0.0, 1.0 - float(distance)), 4)
        })
    return output

def list_documents():
    collection = get_collection()
    if collection.count() == 0:
        return []
    data = collection.get(include=["metadatas"])
    unique = {}
    for meta in data.get("metadatas", []):
        unique[meta["document_id"]] = {
            "document_id": meta["document_id"],
            "filename": meta["filename"]
        }
    return list(unique.values())
