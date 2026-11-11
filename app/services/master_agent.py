"""
Master Agent & Central Orchestrator
The core coordinator for Veritas AI:
1. Evaluates user intent & detects ambiguity / clarification requirements.
2. Decomposes inquiries into specialized sub-tasks.
3. Delegates tasks to Research Agent, Knowledge Base, and Analysis Agents.
4. Collects and organizes all sub-agent evidence and counter-arguments.
5. Runs the Evidence Verification Engine with deterministic rubric scoring.
6. Synthesizes executive summary and detailed deliverable with citations and limitations.
7. Produces downloadable executive PDF reports and maintains full execution traces.
"""

import time
import datetime
from typing import Dict, Any, List, Optional
from app.config import settings
from app.schemas import (
    MasterOrchestrationRequest,
    MasterOrchestrationResponse,
    Source,
    SubTaskStatus
)
from app.services.task_decomposer import decompose_query
from app.services.subagent_coordinator import coordinate_subagents
from app.services.verifier import verify_evidence_and_claims
from app.services.synthesis import generate_synthesis
from app.services.pdf_generator import generate_pdf_report

# In-memory execution trace / task store for API inspection
TASK_REGISTRY: Dict[str, Dict[str, Any]] = {}

def get_task_trace(task_id: str) -> Optional[Dict[str, Any]]:
    return TASK_REGISTRY.get(task_id)


def run_master_orchestration(request: MasterOrchestrationRequest) -> MasterOrchestrationResponse:
    """
    Executes the end-to-end Master Agent workflow.
    """
    start_time = time.time()
    trace_events: List[Dict[str, Any]] = []

    def log_event(stage: str, detail: str, data: Optional[Dict[str, Any]] = None):
        trace_events.append({
            "stage": stage,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "detail": detail,
            "data": data or {}
        })

    log_event("initiation", f"Received query: '{request.query}'", {"room_id": request.room_id})

    # Step 1: Query Understanding & Intent Clarification
    log_event("decomposition", "Analyzing query and formulating sub-task plan...")
    plan = decompose_query(
        query=request.query,
        include_web=request.include_web,
        include_kb=request.include_knowledge_base
    )

    if plan.intent_clarification_needed:
        log_event("clarification_needed", "Query is ambiguous or under-specified; requesting user clarification.")
        response = MasterOrchestrationResponse(
            task_id=plan.task_id,
            query=request.query,
            status="clarification_needed",
            clarification_needed=True,
            clarification_prompt=plan.clarification_prompt,
            executive_summary=(
                "**Clarification Required**: The request is too broad or ambiguous for authoritative verification.\n"
                f"{plan.clarification_prompt}"
            ),
            final_synthesis=plan.clarification_prompt or "",
            evidence_strength={
                "overall_score": 0,
                "label": "heuristic",
                "verified_claims_count": 0,
                "partially_supported_count": 0,
                "disputed_claims_count": 0,
                "unverified_claims_count": 0,
                "rubric_breakdown": {},
                "explanation": "Clarification required prior to task execution.",
                "deductions": ["Request was not actionable without additional scope."]
            },
            claims=[],
            subtasks=[],
            citations=[],
            sources=[],
            limitations=["Under-specified query; execution halted to prevent inaccurate or fabricated results."],
            trace=trace_events
        )
        TASK_REGISTRY[plan.task_id] = response.model_dump()
        return response

    log_event("plan_created", f"Created {len(plan.subtasks)} sub-tasks across specialized agents.", {
        "domain": plan.detected_domain,
        "subtask_count": len(plan.subtasks)
    })

    # Step 2: Sub-Agent Delegation & Evidence Collection
    log_event("delegation", f"Delegating {len(plan.subtasks)} sub-tasks to specialized sub-agents...")
    completed_subtasks, all_evidence, all_objections = coordinate_subagents(
        subtasks=plan.subtasks,
        top_k=request.top_k
    )
    log_event("evidence_collected", f"Collected {len(all_evidence)} evidence items and {len(all_objections)} counter-analysis objections.", {
        "evidence_count": len(all_evidence),
        "objection_count": len(all_objections)
    })

    # Step 3: Evidence Verification & Deterministic Rubric Scoring
    log_event("verification", "Running claim-level verification engine and applying deterministic 5-criterion rubric...")
    claims, evidence_strength = verify_evidence_and_claims(
        claims_text_or_list="",
        evidence=all_evidence,
        objections=all_objections
    )
    log_event("verification_complete", f"Evidence-strength score: {evidence_strength.overall_score}/100. Verified: {evidence_strength.verified_claims_count}, Disputed: {evidence_strength.disputed_claims_count}.", {
        "overall_score": evidence_strength.overall_score,
        "breakdown": evidence_strength.rubric_breakdown
    })

    # Step 4: Master Synthesis
    log_event("synthesis", "Synthesizing executive summary and reconciling sub-agent perspectives...")
    exec_summary, final_synthesis, citations, limitations = generate_synthesis(
        query=request.query,
        claims=claims,
        evidence_strength=evidence_strength,
        subtasks=completed_subtasks,
        objections=all_objections
    )

    # Step 5: Extract unique sources for display
    unique_sources: Dict[str, Source] = {}
    for ev in all_evidence:
        if ev.url_or_id and ev.url_or_id not in unique_sources:
            unique_sources[ev.url_or_id] = Source(
                title=ev.source_title,
                url=ev.url_or_id,
                source_type=ev.source_type
            )
    sources_list = list(unique_sources.values())

    # Step 6: Generate Executive PDF Report
    report_id = None
    pdf_download_url = None
    if request.generate_pdf:
        log_event("pdf_generation", "Rendering executive ReportLab PDF report...")
        try:
            report_meta = generate_pdf_report(
                task_id=plan.task_id,
                query=request.query,
                executive_summary=exec_summary,
                final_synthesis=final_synthesis,
                evidence_strength=evidence_strength,
                claims=claims,
                sources=sources_list,
                citations=citations,
                limitations=limitations
            )
            report_id = report_meta["report_id"]
            pdf_download_url = report_meta["download_url"]
            log_event("pdf_generated", f"PDF report generated: {report_meta['filename']} ({report_meta['file_size_bytes']} bytes)")
        except Exception as exc:
            log_event("pdf_failed", f"PDF report generation failed: {str(exc)}")
            limitations.append(f"PDF generation encountered an error: {type(exc).__name__}")

    execution_duration_ms = int((time.time() - start_time) * 1000)
    log_event("completion", f"Master orchestration completed in {execution_duration_ms}ms.")

    response = MasterOrchestrationResponse(
        task_id=plan.task_id,
        query=request.query,
        status="completed",
        clarification_needed=False,
        clarification_prompt=None,
        executive_summary=exec_summary,
        final_synthesis=final_synthesis,
        evidence_strength=evidence_strength,
        claims=claims,
        subtasks=completed_subtasks,
        citations=citations,
        sources=sources_list,
        limitations=limitations,
        report_id=report_id,
        pdf_download_url=pdf_download_url,
        trace=trace_events
    )

    TASK_REGISTRY[plan.task_id] = response.model_dump()
    return response
