"""
Task Decomposition & Query Understanding Module
Responsible for:
1. Parsing user queries and detecting intent / ambiguity.
2. Formulating clarification questions when requests are too vague.
3. Breaking actionable queries into specialized sub-tasks:
   - Research (Web)
   - Knowledge Base (Internal Docs)
   - Domain Analysis
   - Counter-Analysis / Red-Teaming
"""

import uuid
import re
from typing import Dict, Any, List, Tuple
from app.config import settings
from app.schemas import TaskPlan, SubTask, SubTaskType, SubTaskStatus
import requests

# Domain keyword markers
DOMAIN_KEYWORDS = {
    "energy": ["solar", "wind", "battery", "grid", "renewable", "nuclear", "power", "storage", "hydrogen", "electric"],
    "technology": ["ai", "llm", "software", "api", "cloud", "security", "hardware", "algorithm", "database", "agent"],
    "finance": ["market", "investment", "cost", "revenue", "inflation", "stock", "yield", "funding", "crypto", "budget"],
    "healthcare": ["clinical", "medical", "drug", "fda", "health", "hospital", "patient", "vaccine", "treatment"],
    "governance": ["policy", "regulation", "law", "compliance", "standard", "government", "act", "mandate"]
}

VAGUE_QUERY_PATTERNS = [
    r"^(hi|hello|hey|test|ping)$",
    r"^what do you think\??$",
    r"^tell me more\??$",
    r"^is it good\??$",
    r"^explain this\??$",
    r"^compare them\??$"
]

def detect_ambiguity(query: str) -> Tuple[bool, str]:
    """
    Checks if a user query is too ambiguous or under-specified to execute expensive research.
    Returns (is_ambiguous, clarification_prompt).
    """
    cleaned = query.strip().lower()
    if len(cleaned.split()) < 3 and not any(k in cleaned for domain in DOMAIN_KEYWORDS.values() for k in domain):
        return True, (
            f"Your request '{query}' is brief or missing specific scope. "
            "Please specify: 1) The exact topic or technology, 2) The specific question or metric you want investigated, "
            "and 3) Any key constraints (e.g., timeframe or geography)."
        )

    for pat in VAGUE_QUERY_PATTERNS:
        if re.match(pat, cleaned):
            return True, (
                f"Your query '{query}' is broad. What specific system, technology, or topic would you like "
                "the Veritas AI agent team to research and verify?"
            )

    return False, ""


def classify_domain(query: str) -> str:
    """
    Classifies the domain of a query based on keyword analysis.
    """
    query_lower = query.lower()
    for domain, kws in DOMAIN_KEYWORDS.items():
        if any(kw in query_lower for kw in kws):
            return domain
    return "general"


def decompose_query(query: str, include_web: bool = True, include_kb: bool = True) -> TaskPlan:
    """
    Breaks a user query into coordinated sub-tasks for specialized sub-agents.
    """
    task_id = f"task-{uuid.uuid4().hex[:8]}"
    is_ambiguous, clarification_prompt = detect_ambiguity(query)

    if is_ambiguous:
        return TaskPlan(
            task_id=task_id,
            original_query=query,
            intent_clarification_needed=True,
            clarification_prompt=clarification_prompt,
            detected_domain="unspecified",
            subtasks=[],
            estimated_effort="low"
        )

    domain = classify_domain(query)
    subtasks: List[SubTask] = []

    # 1. Research Agent Subtask (Authoritative Web Retrieval)
    if include_web:
        subtasks.append(SubTask(
            id=f"{task_id}-sub-1",
            title="External Web Research",
            task_type=SubTaskType.RESEARCH,
            description="Retrieve primary and authoritative external sources, metrics, and latest public publications.",
            query=query,
            assigned_agent="ResearchAgent",
            status=SubTaskStatus.PENDING
        ))

    # 2. Knowledge-Base Agent Subtask (Internal Retrieval)
    if include_kb:
        subtasks.append(SubTask(
            id=f"{task_id}-sub-2",
            title="Internal Knowledge Base Retrieval",
            task_type=SubTaskType.KNOWLEDGE_BASE,
            description="Search local knowledge base chunks, internal project documents, and team references.",
            query=query,
            assigned_agent="KnowledgeBaseAgent",
            status=SubTaskStatus.PENDING
        ))

    # 3. Domain Analysis Agent Subtask (Interpretation & Feasibility)
    subtasks.append(SubTask(
        id=f"{task_id}-sub-3",
        title=f"{domain.capitalize()} Domain Analysis",
        task_type=SubTaskType.DOMAIN_ANALYSIS,
        description=f"Analyze retrieved evidence in the context of {domain} technical principles, metrics, and feasibility.",
        query=f"Analyze {domain} implications and core claims for: {query}",
        assigned_agent="AnalysisAgent",
        status=SubTaskStatus.PENDING
    ))

    # 4. Counter-Analysis & Red-Teaming Subtask (Adversarial Checking)
    subtasks.append(SubTask(
        id=f"{task_id}-sub-4",
        title="Adversarial Counter-Analysis",
        task_type=SubTaskType.COUNTER_ANALYSIS,
        description="Identify counter-evidence, hidden assumptions, opposing studies, and potential failure modes.",
        query=f"Counter-arguments, challenges, and limitations regarding: {query}",
        assigned_agent="CounterAnalysisAgent",
        status=SubTaskStatus.PENDING
    ))

    return TaskPlan(
        task_id=task_id,
        original_query=query,
        intent_clarification_needed=False,
        clarification_prompt=None,
        detected_domain=domain,
        subtasks=subtasks,
        estimated_effort="high" if len(subtasks) >= 4 else "medium"
    )
