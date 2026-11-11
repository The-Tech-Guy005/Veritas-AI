import pytest
from app.services.master_agent import run_master_orchestration, get_task_trace
from app.schemas import MasterOrchestrationRequest

def test_master_agent_clarification_on_vague_query():
    req = MasterOrchestrationRequest(
        query="hi",
        include_web=False,
        include_knowledge_base=False,
        generate_pdf=False
    )
    res = run_master_orchestration(req)
    assert res.status == "clarification_needed"
    assert res.clarification_needed is True
    assert res.clarification_prompt is not None
    assert len(res.subtasks) == 0

def test_master_agent_end_to_end_orchestration():
    req = MasterOrchestrationRequest(
        query="What are the recent efficiency advancements in perovskite tandem solar cells?",
        include_web=False,
        include_knowledge_base=False,
        generate_pdf=True
    )
    res = run_master_orchestration(req)
    assert res.status == "completed"
    assert res.clarification_needed is False
    assert len(res.subtasks) > 0
    assert res.evidence_strength is not None
    assert res.evidence_strength.overall_score >= 0
    assert res.report_id is not None
    assert res.pdf_download_url is not None
    assert len(res.trace) > 0

    # Test trace retrieval
    stored_trace = get_task_trace(res.task_id)
    assert stored_trace is not None
    assert stored_trace["task_id"] == res.task_id

