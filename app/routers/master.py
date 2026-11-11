import os
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from app.config import settings
from app.schemas import (
    MasterOrchestrationRequest,
    MasterOrchestrationResponse,
    DecompositionRequest,
    DecompositionResponse,
    ClaimVerificationRequest,
    ClaimVerificationResponse,
    SynthesisRequest,
    SynthesisResponse
)
from app.services.master_agent import run_master_orchestration, get_task_trace
from app.services.task_decomposer import decompose_query
from app.services.verifier import verify_evidence_and_claims
from app.services.synthesis import generate_synthesis

router = APIRouter(prefix="/master")

@router.post("/orchestrate", response_model=MasterOrchestrationResponse, summary="Execute full Master Agent orchestration workflow")
def orchestrate(request: MasterOrchestrationRequest):
    """
    Coordinates the entire Veritas AI multi-agent workflow:
    1. Understands query intent and checks for ambiguity.
    2. Decomposes inquiry into sub-tasks (Research, KB, Domain Analysis, Counter-Analysis).
    3. Delegates tasks to specialized sub-agents.
    4. Gathers, verifies, and scores evidence with the deterministic 5-criterion rubric.
    5. Synthesizes executive summary, counter-arguments, and limitations.
    6. Generates a downloadable executive PDF report.
    """
    return run_master_orchestration(request)


@router.post("/decompose", response_model=DecompositionResponse, summary="Decompose user query into sub-tasks")
def decompose(request: DecompositionRequest):
    """
    Analyzes query and produces a structured TaskPlan with assigned sub-agents.
    """
    plan = decompose_query(request.query)
    return DecompositionResponse(plan=plan)


@router.post("/verify", response_model=ClaimVerificationResponse, summary="Run claim verification & rubric scoring")
def verify_claims(request: ClaimVerificationRequest):
    """
    Applies the deterministic 5-criterion evidence rubric to assess and score claims.
    """
    claims, score = verify_evidence_and_claims(
        claims_text_or_list=request.claims,
        evidence=request.evidence,
        objections=[]
    )
    return ClaimVerificationResponse(claims=claims, evidence_strength=score)


@router.post("/synthesize", response_model=SynthesisResponse, summary="Synthesize final response from verified claims")
def synthesize(request: SynthesisRequest):
    """
    Synthesizes executive summary and detailed deliverable from verified claims.
    """
    exec_summary, detailed, citations, limitations = generate_synthesis(
        query=request.query,
        claims=request.claims,
        evidence_strength=request.evidence_strength,
        subtasks=request.subtasks,
        objections=[]
    )
    return SynthesisResponse(
        executive_summary=exec_summary,
        final_synthesis=detailed,
        citations=citations,
        limitations=limitations
    )


@router.get("/reports/{report_id}/pdf", summary="Download executive verification PDF report")
def download_pdf(report_id: str):
    """
    Serves the generated ReportLab PDF deliverable.
    """
    safe_id = os.path.basename(report_id)
    if not safe_id.endswith(".pdf"):
        safe_id = f"{safe_id}.pdf"
    file_path = os.path.join(settings.reports_dir, safe_id)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Report PDF not found")
    return FileResponse(
        file_path,
        media_type="application/pdf",
        filename=safe_id
    )


@router.get("/trace/{task_id}", summary="Get task execution trace")
def get_trace(task_id: str):
    """
    Returns step-by-step execution log and timestamps for an orchestration task.
    """
    trace = get_task_trace(task_id)
    if not trace:
        raise HTTPException(status_code=404, detail=f"Task trace for '{task_id}' not found.")
    return trace

