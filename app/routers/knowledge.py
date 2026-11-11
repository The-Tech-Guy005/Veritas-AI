from fastapi import APIRouter, Query
from app.schemas import KnowledgeSearchRequest
from app.services.vector_store import search_chunks
from app.services.demo_kb import seed_demo_knowledge_base, get_demo_kb_status

router = APIRouter()

@router.post("/knowledge-base/search", summary="Search knowledge base with document-level access control")
def knowledge_search(request: KnowledgeSearchRequest):
    """
    Performs semantic vector search across indexed documents.
    Applies document-level access control to filter results by user roles and classification.
    """
    results = search_chunks(
        query=request.query,
        top_k=request.top_k,
        user_roles=request.user_roles,
        user_id=request.user_id,
        max_classification=request.max_classification
    )
    return {"query": request.query, "results": results}


@router.post("/knowledge-base/seed-demo", summary="Seed curated multi-domain demo knowledge base")
def seed_demo(force: bool = Query(False, description="Whether to re-index demo documents even if already present")):
    """
    Initializes the curated demo knowledge base with authoritative reference materials:
    - DOE Clean Energy Progress Report (.gov)
    - Nature AI Safety & Multi-Agent Benchmarks (Peer-Reviewed)
    - Reuters Semiconductor Supply Chain Analysis (Wire)
    - Veritas AI Architectural Specification (Internal Team KB)
    - Executive Strategic Roadmap Presentation (PPTX Multi-Slide Deck)
    """
    return seed_demo_knowledge_base(force=force)


@router.get("/knowledge-base/demo-status", summary="Get status of curated demo knowledge base")
def demo_status():
    """
    Returns installation status and overview of documents in the curated demo knowledge base.
    """
    return get_demo_kb_status()
