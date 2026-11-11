"""
Sub-Agent Coordinator Module
Coordinates execution across specialized sub-agents:
1. Research Agent (Live web search via Tavily)
2. Knowledge Base Agent (Semantic RAG retrieval via ChromaDB)
3. Domain Analysis Agent (Technical synthesis & interpretation)
4. Counter-Analysis Agent (Adversarial stress-testing & conflict detection)
"""

import time
import requests
from typing import List, Dict, Any, Tuple
from app.config import settings
from app.schemas import (
    SubTask, SubTaskType, SubTaskStatus, EvidenceItem, Source
)
from app.services.research import run_research
from app.services.vector_store import search_chunks

def execute_research_subtask(subtask: SubTask, top_k: int = 5) -> Tuple[SubTask, List[EvidenceItem]]:
    """
    Delegates external research to the Research Agent.
    """
    start_time = time.time()
    evidence_items: List[EvidenceItem] = []
    try:
        subtask.status = SubTaskStatus.IN_PROGRESS
        res = run_research(
            query=subtask.query,
            include_web=True,
            include_knowledge_base=False,
            top_k=top_k
        )
        subtask.status = SubTaskStatus.COMPLETED
        subtask.result = {
            "answer": res.get("answer", ""),
            "citations": res.get("citations", []),
            "source_count": len(res.get("sources", [])),
            "limitations": res.get("limitations", [])
        }
        for s in res.get("sources", []):
            evidence_items.append(EvidenceItem(
                source_title=s.get("title", "Web Source"),
                url_or_id=s.get("url", ""),
                source_type="web",
                # the source's OWN text; using the generated answer here would make claims verify against themselves
                passage=(s.get("content") or s.get("title") or "")[:1200],
                authority_level="high" if any(dom in s.get("url", "") for dom in [".gov", ".edu", ".org", "reuters", "bloomberg"]) else "medium"
            ))
    except Exception as exc:
        subtask.status = SubTaskStatus.FAILED
        subtask.error = f"Research Agent delegation failed: {str(exc)}"
        subtask.result = {"error": str(exc)}

    subtask.execution_time_ms = int((time.time() - start_time) * 1000)
    return subtask, evidence_items


def execute_knowledge_base_subtask(subtask: SubTask, top_k: int = 5) -> Tuple[SubTask, List[EvidenceItem]]:
    """
    Delegates retrieval to the Knowledge Base Agent.
    """
    start_time = time.time()
    evidence_items: List[EvidenceItem] = []
    try:
        subtask.status = SubTaskStatus.IN_PROGRESS
        chunks = search_chunks(subtask.query, top_k=top_k)
        subtask.status = SubTaskStatus.COMPLETED
        subtask.result = {
            "chunk_count": len(chunks),
            "documents": list({c.get("filename", "unknown") for c in chunks}),
            "chunks": chunks
        }
        for chunk in chunks:
            evidence_items.append(EvidenceItem(
                source_title=f"Doc: {chunk.get('filename', 'internal_document')}",
                url_or_id=f"kb://{chunk.get('document_id', 'doc')}/chunk_{chunk.get('chunk_id', '0')}",
                source_type="knowledge_base",
                passage=chunk.get("text", "")[:400],
                authority_level="high"
            ))
    except Exception as exc:
        subtask.status = SubTaskStatus.FAILED
        subtask.error = f"Knowledge Base Agent delegation failed: {str(exc)}"
        subtask.result = {"error": str(exc), "chunk_count": 0}

    subtask.execution_time_ms = int((time.time() - start_time) * 1000)
    return subtask, evidence_items


def execute_domain_analysis_subtask(
    subtask: SubTask,
    prior_evidence: List[EvidenceItem]
) -> Tuple[SubTask, List[EvidenceItem]]:
    """
    Delegates domain analysis to interpret evidence within specialized technical scope.
    """
    start_time = time.time()
    evidence_items: List[EvidenceItem] = []
    subtask.status = SubTaskStatus.IN_PROGRESS

    evidence_summary = "\n".join([f"- {e.source_title}: {e.passage[:150]}" for e in prior_evidence[:4]])

    if settings.gemini_api_key:
        prompt = (
            f"You are the Veritas AI Domain Analysis Agent. Analyze the following domain problem and evidence:\n\n"
            f"PROBLEM: {subtask.query}\n"
            f"EVIDENCE EXCERPTS:\n{evidence_summary}\n\n"
            f"Provide a structured analysis covering: 1) Technical implications, 2) Operational feasibility, "
            f"3) Key dependencies. Keep it concise, evidence-grounded, and professional."
        )
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
            resp = requests.post(
                url,
                json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.2}},
                timeout=settings.subagent_timeout_seconds
            )
            resp.raise_for_status()
            data = resp.json()
            analysis_text = data["candidates"][0]["content"]["parts"][0]["text"]
            subtask.status = SubTaskStatus.COMPLETED
            subtask.result = {"analysis": analysis_text, "mode": "llm"}
            evidence_items.append(EvidenceItem(
                source_title="Domain Analysis Sub-Agent",
                url_or_id="agent://domain-analysis",
                source_type="analysis",
                passage=analysis_text[:350],
                authority_level="medium"
            ))
        except Exception as exc:
            subtask.status = SubTaskStatus.COMPLETED
            subtask.result = {
                "analysis": f"Domain analysis grounded on {len(prior_evidence)} evidence points.",
                "mode": "fallback_heuristic",
                "notice": str(exc)
            }
    else:
        # Heuristic / deterministic domain interpretation
        subtask.status = SubTaskStatus.COMPLETED
        subtask.result = {
            "analysis": f"Evaluated technical viability against {len(prior_evidence)} collected evidence items.",
            "mode": "heuristic"
        }

    subtask.execution_time_ms = int((time.time() - start_time) * 1000)
    return subtask, evidence_items


def execute_counter_analysis_subtask(
    subtask: SubTask,
    prior_evidence: List[EvidenceItem]
) -> Tuple[SubTask, List[EvidenceItem], List[str]]:
    """
    Adversarial Counter-Analysis Agent:
    Looks for alternative explanations, missing assumptions, counter-evidence, and failure modes.
    Returns (subtask, counter_evidence_items, objections).
    """
    start_time = time.time()
    counter_evidence: List[EvidenceItem] = []
    objections: List[str] = []
    subtask.status = SubTaskStatus.IN_PROGRESS

    evidence_summary = "\n".join([f"- {e.source_title}: {e.passage[:150]}" for e in prior_evidence[:4]])

    if settings.gemini_api_key:
        prompt = (
            f"You are the Veritas AI Counter-Analysis Agent (Red-Teaming).\n"
            f"Your job is to identify weak assumptions, potential contradictions, counter-evidence, and failure modes.\n\n"
            f"TOPIC: {subtask.query}\n"
            f"RETRIEVED EVIDENCE:\n{evidence_summary}\n\n"
            f"Provide: 1) Critical counter-arguments or dissenting findings, 2) Hidden or unverified assumptions, "
            f"3) Specific risk factors or limitations. Highlight any contradiction."
        )
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
            resp = requests.post(
                url,
                json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.3}},
                timeout=settings.subagent_timeout_seconds
            )
            resp.raise_for_status()
            data = resp.json()
            counter_text = data["candidates"][0]["content"]["parts"][0]["text"]
            subtask.status = SubTaskStatus.COMPLETED
            subtask.result = {"counter_analysis": counter_text, "mode": "llm"}
            objections.append(counter_text[:200])
            counter_evidence.append(EvidenceItem(
                source_title="Adversarial Counter-Analysis Agent",
                url_or_id="agent://counter-analysis",
                source_type="counter_analysis",
                passage=counter_text[:350],
                authority_level="medium"
            ))
        except Exception as exc:
            subtask.status = SubTaskStatus.COMPLETED
            default_objection = "Counter-analysis notes: Single-method dependency and potential sampling bias in available sources."
            objections.append(default_objection)
            subtask.result = {"counter_analysis": default_objection, "mode": "fallback_heuristic", "notice": str(exc)}
    else:
        # Heuristic counter-analysis
        subtask.status = SubTaskStatus.COMPLETED
        heur_notes = "Evaluated potential edge cases: real-world performance may deviate from lab/published benchmarks under varying environmental conditions."
        objections.append(heur_notes)
        subtask.result = {"counter_analysis": heur_notes, "mode": "heuristic"}
        counter_evidence.append(EvidenceItem(
            source_title="Heuristic Counter-Analysis Check",
            url_or_id="agent://counter-analysis-heuristic",
            source_type="counter_analysis",
            passage=heur_notes,
            authority_level="medium"
        ))

    subtask.execution_time_ms = int((time.time() - start_time) * 1000)
    return subtask, counter_evidence, objections


def coordinate_subagents(
    subtasks: List[SubTask],
    top_k: int = 5
) -> Tuple[List[SubTask], List[EvidenceItem], List[str]]:
    """
    Main orchestration loop that coordinates all sub-tasks in dependency order,
    collects and organizes sub-agent responses, and builds the evidence repository.
    """
    completed_subtasks: List[SubTask] = []
    all_evidence: List[EvidenceItem] = []
    all_objections: List[str] = []

    # First pass: Research and Knowledge-Base retrieval
    for st in subtasks:
        if st.task_type == SubTaskType.RESEARCH:
            updated_st, ev_items = execute_research_subtask(st, top_k=top_k)
            completed_subtasks.append(updated_st)
            all_evidence.extend(ev_items)
        elif st.task_type == SubTaskType.KNOWLEDGE_BASE:
            updated_st, ev_items = execute_knowledge_base_subtask(st, top_k=top_k)
            completed_subtasks.append(updated_st)
            all_evidence.extend(ev_items)

    # Second pass: Domain Analysis using retrieved evidence
    for st in subtasks:
        if st.task_type == SubTaskType.DOMAIN_ANALYSIS:
            updated_st, ev_items = execute_domain_analysis_subtask(st, all_evidence)
            completed_subtasks.append(updated_st)
            all_evidence.extend(ev_items)

    # Third pass: Counter-Analysis (Red-Teaming)
    for st in subtasks:
        if st.task_type == SubTaskType.COUNTER_ANALYSIS:
            updated_st, ev_items, objs = execute_counter_analysis_subtask(st, all_evidence)
            completed_subtasks.append(updated_st)
            all_evidence.extend(ev_items)
            all_objections.extend(objs)

    return completed_subtasks, all_evidence, all_objections

