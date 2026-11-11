from fastapi import APIRouter
from app.schemas import ResearchRequest, ResearchResponse
from app.services.research import run_research

router = APIRouter()

@router.post("/research", response_model=ResearchResponse)
def research(request: ResearchRequest):
    return run_research(request.query, request.include_web, request.top_k)
