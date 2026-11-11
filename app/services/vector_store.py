"""
Vector Store Service (ChromaDB Integration)
Provides persistent semantic vector search, chunk indexing,
and Document-Level Access Control (RBAC/ABAC).
"""

from pathlib import Path
from typing import List, Dict, Any, Optional
import chromadb
from app.config import settings

CLASSIFICATION_LEVELS = {
    "public": 0,
    "internal": 1,
    "confidential": 2,
    "restricted": 3,
}


def get_collection():
    """
    Returns persistent ChromaDB collection.
    """
    client = chromadb.PersistentClient(path=str(Path(settings.data_dir) / "chroma"))
    return client.get_or_create_collection(
        name=settings.chroma_collection,
        metadata={"hnsw:space": "cosine"}
    )


def is_chunk_authorized(
    meta: Dict[str, Any],
    user_roles: Optional[List[str]] = None,
    user_id: Optional[str] = None,
    max_classification: Optional[str] = None
) -> bool:
    """
    Evaluates document-level access control.
    Enforces role-based permissions and hierarchical data classifications.
    """
    # Unrestricted query (internal system tasks without user filter)
    if user_roles is None and user_id is None and max_classification is None:
        return True

    roles_set = set(r.strip().lower() for r in (user_roles or ["public"]))

    # Super-role override
    if "admin" in roles_set or "superuser" in roles_set:
        return True

    # Document owner override
    doc_owner = str(meta.get("owner_id", "")).strip()
    if user_id and doc_owner and user_id.strip() == doc_owner:
        return True

    # Classification ceiling check
    doc_class = str(meta.get("classification", "public")).lower()
    if max_classification:
        user_max_rank = CLASSIFICATION_LEVELS.get(max_classification.lower(), 1)
        doc_rank = CLASSIFICATION_LEVELS.get(doc_class, 1)
        if doc_rank > user_max_rank:
            return False

    # Role intersection check
    raw_roles = str(meta.get("access_roles", "public")).lower()
    doc_allowed_roles = set(r.strip() for r in raw_roles.split(",") if r.strip())

    # Public documents are accessible to any user with "public" role
    if "public" in doc_allowed_roles and "public" in roles_set:
        return True

    # Check for any shared role
    if bool(roles_set.intersection(doc_allowed_roles)):
        return True

    return False


def add_chunks(
    document_id: str,
    filename: str,
    chunks: List[str],
    classification: str = "public",
    access_roles: Optional[List[str]] = None,
    owner_id: Optional[str] = None,
    source_type: str = "knowledge_base",
    authority_level: str = "medium"
) -> int:
    """
    Indexes document chunks into Chroma with document-level access control metadata.
    """
    if not chunks:
        return 0

    collection = get_collection()
    ids = [f"{document_id}_{i}" for i in range(len(chunks))]

    roles_str = ",".join(access_roles) if access_roles else "public"
    if isinstance(access_roles, str):
        roles_str = access_roles

    metadatas = [
        {
            "document_id": document_id,
            "filename": filename,
            "chunk_id": str(i),
            "classification": classification.lower(),
            "access_roles": roles_str.lower(),
            "owner_id": str(owner_id or ""),
            "source_type": source_type,
            "authority_level": authority_level
        }
        for i in range(len(chunks))
    ]

    collection.upsert(ids=ids, documents=chunks, metadatas=metadatas)
    return len(chunks)


def search_chunks(
    query: str,
    top_k: int = 5,
    user_roles: Optional[List[str]] = None,
    user_id: Optional[str] = None,
    max_classification: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Searches document chunks and filters results according to document-level access controls.
    """
    collection = get_collection()
    count = collection.count()
    if count == 0:
        return []

    # Fetch candidate pool to allow access filtering
    fetch_k = min(count, max(top_k * 4, 15))

    result = collection.query(
        query_texts=[query],
        n_results=fetch_k,
        include=["documents", "metadatas", "distances"]
    )

    output = []
    docs = result.get("documents", [[]])[0]
    metas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]

    for text, meta, distance in zip(docs, metas, distances):
        # Apply document-level access control gate
        if not is_chunk_authorized(meta, user_roles, user_id, max_classification):
            continue

        output.append({
            "text": text,
            "document_id": meta.get("document_id", ""),
            "filename": meta.get("filename", ""),
            "chunk_id": meta.get("chunk_id", ""),
            "classification": meta.get("classification", "public"),
            "access_roles": meta.get("access_roles", "public").split(","),
            "owner_id": meta.get("owner_id", ""),
            "relevance_score": round(max(0.0, 1.0 - float(distance)), 4)
        })

        if len(output) >= top_k:
            break

    return output


def list_documents(user_roles: Optional[List[str]] = None, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Returns unique documents indexed in the vector store, filtered by user authorization.
    """
    collection = get_collection()
    if collection.count() == 0:
        return []

    data = collection.get(include=["metadatas"])
    unique = {}
    for meta in data.get("metadatas", []):
        if not is_chunk_authorized(meta, user_roles, user_id):
            continue
        doc_id = meta["document_id"]
        if doc_id not in unique:
            unique[doc_id] = {
                "document_id": doc_id,
                "filename": meta.get("filename", ""),
                "classification": meta.get("classification", "public"),
                "access_roles": meta.get("access_roles", "public").split(","),
                "owner_id": meta.get("owner_id", "")
            }
    return list(unique.values())


def delete_document(document_id: str) -> int:
    """
    Deletes all chunks associated with a document_id.
    """
    collection = get_collection()
    count_before = collection.count()
    collection.delete(where={"document_id": document_id})
    return count_before - collection.count()
