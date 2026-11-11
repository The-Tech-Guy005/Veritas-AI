import os
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
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
from app.services.master_agent import run_master_orchestration, get_task_trace, get_task_record
from app.services.task_store import list_all_tasks
from app.services.task_decomposer import decompose_query
from app.services.verifier import verify_evidence_and_claims
from app.services.synthesis import generate_synthesis

router = APIRouter(prefix="/master")

@router.post("/orchestrate", response_model=MasterOrchestrationResponse, summary="Execute full Master Agent orchestration workflow")
def orchestrate(request: MasterOrchestrationRequest):
    """
    Coordinates the entire Veritas AI multi-agent workflow:
    1. Understands query intent, scans for prompt-injection threats, and checks for ambiguity.
    2. Decomposes inquiry into sub-tasks (Research, KB, Domain Analysis, Counter-Analysis).
    3. Delegates tasks to specialized sub-agents with live progress tracking.
    4. Gathers, verifies, and scores evidence with the deterministic 5-criterion rubric.
    5. Synthesizes executive summary, counter-arguments, and limitations.
    6. Generates a downloadable executive PDF report.
    7. Persists task state to disk across server restarts.
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
    Send either `claims` (list) or `answer` (raw generated text; claims are extracted from it).
    Each returned claim includes its matched source passages, unsupported parts and detected conflicts.
    """
    claims, score = verify_evidence_and_claims(
        claims_text_or_list=request.claims or (request.answer or ""),
        evidence=request.evidence,
        objections=request.objections
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
    Loaded from persistent disk storage so traces survive server restarts.
    """
    trace = get_task_trace(task_id)
    if not trace:
        raise HTTPException(status_code=404, detail=f"Task trace for '{task_id}' not found.")
    return trace


@router.get("/tasks/{task_id}/progress", summary="Get live task progress update")
def get_progress(task_id: str):
    """
    Returns real-time progress percentage (0-100), current execution stage,
    and status updates for an orchestration task.
    """
    task = get_task_record(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    return {
        "task_id": task_id,
        "status": task.get("status", "unknown"),
        "progress": task.get("progress", 0),
        "stage": task.get("stage", "completed" if task.get("status") == "completed" else "unknown"),
        "message": task.get("message", ""),
        "updated_at": task.get("updated_at", "")
    }


@router.get("/tasks/{task_id}", summary="Get persistent task state and result")
def get_task_by_id(task_id: str):
    """
    Returns the complete persistent task record, including final synthesis,
    rubric scores, subtasks, and report metadata. Survives server restarts.
    """
    task = get_task_record(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    return task


@router.get("/tasks", summary="List all historical and active tasks")
def list_tasks(limit: int = Query(50, ge=1, le=200)):
    """
    Returns a summary list of all tasks persisted across restarts.
    """
    return {"tasks": list_all_tasks(limit=limit)}
