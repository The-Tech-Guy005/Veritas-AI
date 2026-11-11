"""
Evidence Verification Engine
Extracts claims, matches evidence against claim statements,
detects conflicts, and computes deterministic rubric scores.
"""

import re
import requests
from typing import List, Dict, Any, Tuple
from app.config import settings
from app.schemas import EvidenceItem, ClaimRecord, ClaimStatus, EvidenceStrengthScore
from app.services.rubric import score_claim, compute_aggregate_evidence_strength

def extract_claims(raw_text: str, max_claims: int = 5) -> List[str]:
    """
    Extracts key factual statements from synthesized findings or subtask results.
    """
    if not raw_text or len(raw_text.strip()) == 0:
        return []

    if settings.gemini_api_key:
        prompt = (
            "Extract 3 to 5 concise, verifiable, factual claims from the following text.\n"
            "Each claim must be an independent factual statement of 1-2 sentences.\n"
            "Return them as a numbered list with no filler.\n\n"
            f"TEXT:\n{raw_text[:2000]}"
        )
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
            resp = requests.post(
                url,
                json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.1}},
                timeout=settings.subagent_timeout_seconds
            )
            resp.raise_for_status()
            data = resp.json()
            extracted_text = data["candidates"][0]["content"]["parts"][0]["text"]
            lines = [re.sub(r"^\d+[\.\)]\s*", "", line).strip() for line in extracted_text.split("\n") if line.strip()]
            claims = [line for line in lines if len(line) > 15][:max_claims]
            if claims:
                return claims
        except Exception:
            pass

    # Heuristic / deterministic claim extraction
    sentences = re.split(r"(?<=[.!?])\s+", raw_text)
    candidate_claims = []
    for s in sentences:
        s_clean = s.strip()
        # Look for sentences containing numbers, percentages, or concrete assertive phrases
        if len(s_clean) > 20 and len(s_clean) < 220:
            if any(char.isdigit() for char in s_clean) or any(w in s_clean.lower() for w in ["increase", "decrease", "report", "show", "found", "is", "reach", "achieve", "requires"]):
                candidate_claims.append(s_clean)
        if len(candidate_claims) >= max_claims:
            break

    if not candidate_claims and sentences:
        candidate_claims = [s.strip() for s in sentences[:max_claims] if len(s.strip()) > 15]

    return candidate_claims


def detect_conflicts(claim: str, evidence: List[EvidenceItem], objections: List[str]) -> Tuple[bool, bool]:
    """
    Checks if there are conflicts or opposing assertions between the claim and
    the counter-analysis objections or opposing evidence passages.
    Returns (has_conflicts, conflict_resolved).
    """
    claim_lower = claim.lower()
    has_conflicts = False

    # Check for direct opposing signals in objections
    contradictory_terms = ["however", "dispute", "contradict", "fails to", "unproven", "overstated", "inaccurate", "deviate", "limitation"]
    for obj in objections:
        obj_lower = obj.lower()
        if any(term in obj_lower for term in contradictory_terms):
            # Check overlap of claim keywords
            claim_words = {w for w in claim_lower.split() if len(w) > 4}
            matched_words = sum(1 for w in claim_words if w in obj_lower)
            if matched_words >= 2:
                has_conflicts = True
                break

    # If conflicts were found, determine whether the evidence clearly addresses/resolves them
    conflict_resolved = False
    if has_conflicts:
        # If there are 2 or more high-authority sources affirming the claim, the conflict is considered addressed/disclosed
        high_auth_count = sum(1 for e in evidence if e.authority_level == "high")
        if high_auth_count >= 2:
            conflict_resolved = True
        else:
            conflict_resolved = False

    return has_conflicts, conflict_resolved


def verify_evidence_and_claims(
    claims_text_or_list: Any,
    evidence: List[EvidenceItem],
    objections: List[str]
) -> Tuple[List[ClaimRecord], EvidenceStrengthScore]:
    """
    Main verification pipeline:
    1. Extracts or receives candidate claims
    2. Matches each claim against the evidence repository
    3. Detects conflicts and scores claims with the deterministic rubric
    4. Computes aggregate evidence strength score
    """
    if isinstance(claims_text_or_list, str):
        claims = extract_claims(claims_text_or_list)
    else:
        claims = list(claims_text_or_list)

    if not claims and evidence:
        # Fallback to extracting claims from top evidence passages
        combined_text = " ".join([e.passage for e in evidence[:3]])
        claims = extract_claims(combined_text)

    records: List[ClaimRecord] = []
    for claim in claims:
        # Find matching evidence for this specific claim
        matching_sources: List[EvidenceItem] = []
        claim_words = {w.lower() for w in claim.split() if len(w) > 3}

        for ev in evidence:
            passage_lower = ev.passage.lower()
            matched = sum(1 for w in claim_words if w in passage_lower)
            if matched >= 1 or len(evidence) <= 2:
                matching_sources.append(ev)

        # Fallback to all evidence if no strict match
        if not matching_sources and evidence:
            matching_sources = evidence[:2]

        has_conflicts, conflict_resolved = detect_conflicts(claim, matching_sources, objections)
        claim_record = score_claim(
            statement=claim,
            sources=matching_sources,
            has_conflicts=has_conflicts,
            conflict_resolved=conflict_resolved
        )
        records.append(claim_record)

    strength_score = compute_aggregate_evidence_strength(records)
    return records, strength_score
