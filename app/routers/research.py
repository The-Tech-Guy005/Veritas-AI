from fastapi import APIRouter
from app.schemas import ResearchRequest, ResearchResponse
from app.services.research import run_research

router = APIRouter()

@router.post("/research", response_model=ResearchResponse)
def research(request: ResearchRequest):
    return run_research(
        request.query,
        include_web=request.include_web,
        include_knowledge_base=request.include_knowledge_base,
        top_k=request.top_k
    )
