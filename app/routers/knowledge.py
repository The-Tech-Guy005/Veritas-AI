from fastapi import APIRouter
from app.schemas import KnowledgeSearchRequest
from app.services.vector_store import search_chunks

router = APIRouter()

@router.post("/knowledge-base/search")
def knowledge_search(request: KnowledgeSearchRequest):
    return {"query": request.query, "results": search_chunks(request.query, request.top_k)}
