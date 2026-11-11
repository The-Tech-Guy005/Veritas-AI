"""
Master Agent & Central Orchestrator
The core coordinator for Veritas AI:
1. Evaluates user intent, validates against prompt injection, and handles clarification.
2. Decomposes inquiries into specialized sub-tasks.
3. Delegates tasks to Research Agent, Knowledge Base, and Analysis Agents.
4. Collects and organizes all sub-agent evidence and counter-arguments.
5. Runs the Evidence Verification Engine with deterministic rubric scoring.
6. Synthesizes executive summary and detailed deliverable with citations and limitations.
7. Produces downloadable executive PDF reports and maintains full execution traces.
8. Persists all task states to disk so state survives restarts and publishes real-time progress updates.
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
from app.services.verifier import verify_evidence_and_claims, build_verification_summary
from app.services.synthesis import generate_synthesis
from app.services.pdf_generator import generate_pdf_report
from app.services.task_store import save_task, get_task, update_task_progress, list_all_tasks
from app.services.security import validate_query_safety, sanitize_evidence_passage


def get_task_trace(task_id: str) -> Optional[Dict[str, Any]]:
    """
    Returns step-by-step execution trace record for a task.
    Loads from persistent storage so traces survive server restarts.
    """
    return get_task(task_id)


def get_task_record(task_id: str) -> Optional[Dict[str, Any]]:
    """
    Returns full persistent task record including progress, status, and results.
    """
    return get_task(task_id)


def _collect_answer_text(subtasks) -> str:
    """The generated response whose claims must be verified: research answers + LLM domain analysis."""
    parts: List[str] = []
    for st in subtasks:
        res = st.result or {}
        if st.task_type.value == "research" and res.get("answer"):
            ans = res["answer"].strip()
            if ans.lower().startswith(("evidence retrieved for your query", "no evidence found",
                                       "llm synthesis was unavailable")):
                continue
            parts.append(ans)
        elif st.task_type.value == "domain_analysis" and res.get("mode") == "llm" and res.get("analysis"):
            parts.append(res["analysis"])
    return "\n\n".join(parts)


def run_master_orchestration(request: MasterOrchestrationRequest) -> MasterOrchestrationResponse:
    """
    Executes the end-to-end Master Agent workflow with:
    - Persistent task state tracking across restarts
    - Step-by-step progress percentage updates
    - Prompt-injection threat detection & sanitization
    """
    start_time = time.time()
    trace_events: List[Dict[str, Any]] = []

    # Step 0: Security & Prompt-Injection Check
    safety_check = validate_query_safety(request.query)
    effective_query = safety_check["safe_query"]

    # Initial plan creation to establish persistent task_id
    plan = decompose_query(
        query=effective_query,
        include_web=request.include_web,
        include_kb=request.include_knowledge_base
    )
    task_id = plan.task_id

    def log_event(stage: str, progress: int, detail: str, data: Optional[Dict[str, Any]] = None):
        evt = {
            "stage": stage,
            "progress": progress,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "detail": detail,
            "data": data or {}
        }
        trace_events.append(evt)
        update_task_progress(
            task_id=task_id,
            progress=progress,
            stage=stage,
            message=detail,
            extra_data={"query": request.query, "room_id": request.room_id}
        )

    log_event("initiation", 5, f"Received query: '{request.query}'", {
        "room_id": request.room_id,
        "is_safe": safety_check["is_safe"],
        "threats_detected": safety_check["threats"]
    })

    if not safety_check["is_safe"]:
        log_event("prompt_injection_flagged", 8, "Prompt-injection pattern detected; query neutralized.", {
            "risk_score": safety_check["risk_score"],
            "threats": safety_check["threats"]
        })

    # Step 1: Query Understanding & Intent Clarification
    log_event("decomposition", 20, "Analyzing query intent and formulating sub-task plan...")

    if plan.intent_clarification_needed:
        log_event("clarification_needed", 100, "Query is ambiguous or under-specified; requesting user clarification.")
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
        # Persist final response
        task_record = response.model_dump()
        task_record["status"] = "clarification_needed"
        task_record["progress"] = 100
        save_task(plan.task_id, task_record)
        return response

    log_event("plan_created", 30, f"Created {len(plan.subtasks)} sub-tasks across specialized agents.", {
        "domain": plan.detected_domain,
        "subtask_count": len(plan.subtasks)
    })

    # Step 2: Sub-Agent Delegation & Evidence Collection
    log_event("delegation", 45, f"Delegating {len(plan.subtasks)} sub-tasks to specialized sub-agents...")
    completed_subtasks, all_evidence, all_objections = coordinate_subagents(
        subtasks=plan.subtasks,
        top_k=request.top_k
    )

    # Sanitize evidence passages against indirect prompt injection
    for ev in all_evidence:
        ev.passage = sanitize_evidence_passage(ev.passage)

    log_event("evidence_collected", 60, f"Collected {len(all_evidence)} evidence items and {len(all_objections)} counter-analysis objections.", {
        "evidence_count": len(all_evidence),
        "objection_count": len(all_objections)
    })

    # Step 3: Evidence Verification & Deterministic Rubric Scoring
    log_event("verification", 75, "Running claim-level verification engine and applying deterministic 5-criterion rubric...")
    answer_text = _collect_answer_text(completed_subtasks)
    claims, evidence_strength = verify_evidence_and_claims(
        claims_text_or_list=answer_text,
        evidence=all_evidence,
        objections=all_objections
    )
    log_event("verification_complete", 80, f"Evidence-strength score: {evidence_strength.overall_score}/100. Verified: {evidence_strength.verified_claims_count}, Disputed: {evidence_strength.disputed_claims_count}.", {
        "overall_score": evidence_strength.overall_score,
        "breakdown": evidence_strength.rubric_breakdown,
        "claim_summary": build_verification_summary(claims)
    })

    # Step 4: Master Synthesis
    log_event("synthesis", 85, "Synthesizing executive summary and reconciling sub-agent perspectives...")
    exec_summary, final_synthesis, citations, limitations = generate_synthesis(
        query=effective_query,
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
        log_event("pdf_generation", 95, "Rendering executive ReportLab PDF report deliverable...")
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
            log_event("pdf_generated", 98, f"PDF report generated: {report_meta['filename']} ({report_meta['file_size_bytes']} bytes)")
        except Exception as exc:
            log_event("pdf_failed", 98, f"PDF report generation failed: {str(exc)}")
            limitations.append(f"PDF generation encountered an error: {type(exc).__name__}")

    execution_duration_ms = int((time.time() - start_time) * 1000)
    log_event("completion", 100, f"Master orchestration completed in {execution_duration_ms}ms.")

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

    # Persist completed task record to disk so it survives restarts
    task_record = response.model_dump()
    task_record["status"] = "completed"
    task_record["progress"] = 100
    task_record["stage"] = "completed"
    task_record["message"] = "Orchestration completed successfully."
    save_task(plan.task_id, task_record)

    return response
