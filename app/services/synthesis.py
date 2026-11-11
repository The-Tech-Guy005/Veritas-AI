"""
Master Synthesis Engine
Synthesizes verified claims, evidence, and counter-analysis objections
into an executive summary, comprehensive final deliverable, citations, and limitations.
"""

from typing import List, Dict, Any, Tuple
import requests
from app.config import settings
from app.schemas import ClaimRecord, ClaimStatus, EvidenceStrengthScore, SubTask, Source

def generate_synthesis(
    query: str,
    claims: List[ClaimRecord],
    evidence_strength: EvidenceStrengthScore,
    subtasks: List[SubTask],
    objections: List[str]
) -> Tuple[str, str, List[str], List[str]]:
    """
    Synthesizes the final answer.
    Returns (executive_summary, final_synthesis, citations, limitations).
    """
    # Collect citations and sources
    citations_set = set()
    limitations_list = list(evidence_strength.deductions)

    for c in claims:
        for s in c.evidence_sources:
            if s.url_or_id.startswith("http"):
                citations_set.add(s.url_or_id)
            elif s.url_or_id.startswith("kb://"):
                citations_set.add(s.url_or_id)

    citations = sorted(list(citations_set))

    # Format claims breakdown for prompt or fallback
    claims_text = []
    for c in claims:
        status_tag = f"[{c.status.value.upper()}]"
        claims_text.append(f"{status_tag} {c.statement} (Score: {c.rubric_score}/100)")
        if c.limitations:
            limitations_list.extend(c.limitations)

    # Deduplicate limitations
    unique_limitations = list(dict.fromkeys(limitations_list))

    if settings.gemini_api_key:
        prompt = (
            f"You are the Veritas AI Master Agent.\n"
            f"Your job is to synthesize a definitive, evidence-backed answer to the user's inquiry.\n\n"
            f"USER QUERY:\n{query}\n\n"
            f"EVIDENCE STRENGTH SCORE:\n{evidence_strength.explanation}\n\n"
            f"VERIFIED CLAIMS AND STATUSES:\n" + "\n".join(claims_text) + "\n\n"
            f"COUNTER-ANALYSIS & OBJECTIONS:\n" + "\n".join(objections) + "\n\n"
            f"INSTRUCTIONS:\n"
            f"1. Generate an 'EXECUTIVE SUMMARY' (2-3 concise paragraphs with bullet points highlighting key verified findings and evidence strength).\n"
            f"2. Generate a 'DETAILED SYNTHESIS' (detailed breakdown of domain findings, verification notes on supported vs disputed claims, counter-evidence considerations, and operational implications).\n"
            f"3. Strictly adhere to evidence. Do not hallucinate or invent citations.\n"
            f"Separate the two sections with the delimiter '---DETAILED_SYNTHESIS---'."
        )
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
            resp = requests.post(
                url,
                json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.2}},
                timeout=settings.subagent_timeout_seconds + 15
            )
            resp.raise_for_status()
            data = resp.json()
            full_text = data["candidates"][0]["content"]["parts"][0]["text"]
            if "---DETAILED_SYNTHESIS---" in full_text:
                parts = full_text.split("---DETAILED_SYNTHESIS---")
                exec_summary = parts[0].replace("EXECUTIVE SUMMARY", "").strip("#:\n ")
                detailed = parts[1].strip("#:\n ")
                return exec_summary, detailed, citations, unique_limitations
            else:
                return full_text[:400], full_text, citations, unique_limitations
        except Exception:
            pass

    # Deterministic / Heuristic synthesis fallback
    verified_claims = [c.statement for c in claims if c.status == ClaimStatus.VERIFIED]
    partially_claims = [c.statement for c in claims if c.status == ClaimStatus.PARTIALLY_SUPPORTED]
    disputed_claims = [c.statement for c in claims if c.status == ClaimStatus.DISPUTED]

    summary_lines = [
        f"**Veritas AI Executive Summary**",
        f"**Topic:** {query}",
        f"**Evidence Strength:** {evidence_strength.overall_score}/100 ({evidence_strength.label.capitalize()})",
        "",
        "**Key Findings:**"
    ]
    if verified_claims:
        for vc in verified_claims:
            summary_lines.append(f"• [Verified] {vc}")
    elif partially_claims:
        for pc in partially_claims:
            summary_lines.append(f"• [Partially Supported] {pc}")
    else:
        summary_lines.append("• Preliminary evidence gathered; further independent corroboration recommended.")

    if disputed_claims:
        summary_lines.append("\n**Contradictions / Disputed Items:**")
        for dc in disputed_claims:
            summary_lines.append(f"• [Disputed] {dc}")

    exec_summary = "\n".join(summary_lines)

    # Detailed synthesis
    detail_lines = [
        f"# Veritas AI Master Synthesis: {query}",
        "",
        f"## 1. Evidence-Strength Assessment",
        f"{evidence_strength.explanation}",
        "",
        "### Rubric Criteria Breakdown:",
        f"- Source Authority: {evidence_strength.rubric_breakdown.get('source_authority', 0)}/30",
        f"- Independent Corroboration: {evidence_strength.rubric_breakdown.get('independent_corroboration', 0)}/25",
        f"- Direct Relevance: {evidence_strength.rubric_breakdown.get('direct_relevance', 0)}/20",
        f"- Recency: {evidence_strength.rubric_breakdown.get('recency', 0)}/15",
        f"- Contradiction Handling: {evidence_strength.rubric_breakdown.get('contradiction_handling', 0)}/10",
        "",
        "## 2. Claim-Level Verification Records"
    ]
    for c in claims:
        detail_lines.append(f"- **Claim:** {c.statement}")
        detail_lines.append(f"  - **Status:** `{c.status.value.upper()}` | **Score:** {c.rubric_score}/100")
        detail_lines.append(f"  - **Quality:** {c.source_quality.capitalize()} source")
        if c.limitations:
            detail_lines.append(f"  - **Limitations:** {', '.join(c.limitations)}")

    if objections:
        detail_lines.append("")
        detail_lines.append("## 3. Adversarial Counter-Analysis & Stress-Testing")
        for obj in objections:
            detail_lines.append(f"- {obj}")

    detail_lines.append("")
    detail_lines.append("## 4. Uncertainty & Scope Limitations")
    if unique_limitations:
        for lim in unique_limitations:
            detail_lines.append(f"- {lim}")
    else:
        detail_lines.append("- No critical evidence anomalies detected.")

    detailed = "\n".join(detail_lines)
    return exec_summary, detailed, citations, unique_limitations

