"""
Deterministic Evidence Verification Rubric
Implements the 5-criterion evidence strength rubric specified in Veritas AI Blueprint:
1. Source Authority (Max 30)
2. Independent Corroboration (Max 25)
3. Direct Relevance (Max 20)
4. Recency (Max 15)
5. Contradiction Handling (Max 10)
Total: 100 points
"""

from typing import List, Dict, Tuple, Any
import datetime
from app.schemas import EvidenceItem, ClaimRecord, ClaimStatus, ClaimRelationship, EvidenceStrengthScore

# Known high-authority domain patterns
HIGH_AUTHORITY_PATTERNS = [
    ".gov", ".edu", ".org", "ieee.org", "nature.com", "sciencedirect.com",
    "reuters.com", "bloomberg.com", "who.int", "un.org", "arxiv.org",
    "worldbank.org", "imf.org", "nasa.gov", "whitehouse.gov", "nih.gov",
    "internal_kb", "official"
]

MEDIUM_AUTHORITY_PATTERNS = [
    ".com", ".net", "techcrunch.com", "bbc.com", "forbes.com",
    "wsj.com", "ft.com", "economist.com", "theguardian.com", "nytimes.com"
]

def assess_source_authority(sources: List[EvidenceItem]) -> Tuple[int, List[str]]:
    """
    Score source authority (0-30 points).
    """
    if not sources:
        return 0, ["No sources provided (-30 pts)."]

    max_auth = 0
    notes = []
    has_high = False
    has_kb = False

    for src in sources:
        url_lower = src.url_or_id.lower()
        if src.source_type == "knowledge_base" or "kb" in url_lower:
            has_kb = True
            max_auth = max(max_auth, 28)
        elif any(pattern in url_lower for pattern in HIGH_AUTHORITY_PATTERNS) or src.authority_level == "high":
            has_high = True
            max_auth = max(max_auth, 30)
        elif any(pattern in url_lower for pattern in MEDIUM_AUTHORITY_PATTERNS) or src.authority_level == "medium":
            max_auth = max(max_auth, 20)
        else:
            max_auth = max(max_auth, 12)

    if has_high:
        notes.append("High-authority authoritative source verified (+30 pts).")
        return 30, notes
    elif has_kb:
        notes.append("Verified internal team knowledge-base document cited (+28 pts).")
        return 28, notes
    elif max_auth >= 20:
        notes.append("Secondary or reputable industry source cited; lacks primary peer-reviewed/official authority (-10 pts).")
        return 20, notes
    else:
        notes.append("Low-authority or unverified domain (-18 pts).")
        return 12, notes


def assess_independent_corroboration(sources: List[EvidenceItem]) -> Tuple[int, List[str]]:
    """
    Score independent corroboration (0-25 points).
    """
    if not sources:
        return 0, ["No independent corroboration (-25 pts)."]

    # Count distinct domains or document IDs
    distinct_origins = set()
    for src in sources:
        origin = src.url_or_id.split("/")[2] if "://" in src.url_or_id else src.url_or_id
        distinct_origins.add(origin)

    count = len(distinct_origins)
    if count >= 3:
        return 25, ["Three or more independent sources corroborate this finding (+25 pts)."]
    elif count == 2:
        return 22, ["Two independent sources corroborate this finding (+22 pts)."]
    elif count == 1:
        return 14, ["Single source cited without independent corroboration (-11 pts)."]
    else:
        return 0, ["No corroborating sources found (-25 pts)."]


def assess_direct_relevance(claim: str, sources: List[EvidenceItem]) -> Tuple[int, List[str]]:
    """
    Score direct relevance (0-20 points).
    Evaluates whether the cited text passages directly support the specific claim words.
    """
    if not sources:
        return 0, ["No evidence passage provided (-20 pts)."]

    claim_words = {w.lower().strip(".,;:?!\"'") for w in claim.split() if len(w) > 3}
    if not claim_words:
        return 15, ["Short or general claim statement (+15 pts)."]

    best_match_ratio = 0.0
    for src in sources:
        passage_lower = src.passage.lower()
        matched = sum(1 for w in claim_words if w in passage_lower)
        ratio = matched / len(claim_words)
        if ratio > best_match_ratio:
            best_match_ratio = ratio

    if best_match_ratio >= 0.7:
        return 20, ["Cited passage directly supports the claim wording (+20 pts)."]
    elif best_match_ratio >= 0.4:
        return 14, ["Cited passage partially supports claim, but requires inference (-6 pts)."]
    elif best_match_ratio > 0.1:
        return 8, ["Cited passage is only tangentially related (-12 pts)."]
    else:
        return 4, ["Cited evidence does not clearly cover key claim concepts (-16 pts)."]


def assess_recency(sources: List[EvidenceItem]) -> Tuple[int, List[str]]:
    """
    Score recency (0-15 points).
    """
    if not sources:
        return 0, ["Undated source (-15 pts)."]

    current_year = datetime.datetime.now(datetime.timezone.utc).year
    has_recent = False
    has_dated = False
    has_no_date = False

    for src in sources:
        date_str = src.publication_date
        if not date_str:
            has_no_date = True
            continue
        try:
            # Extract 4-digit year
            import re
            years = re.findall(r"\b(19\d\d|20\d\d)\b", date_str)
            if years:
                year = int(years[-1])
                if current_year - year <= 2:
                    has_recent = True
                elif current_year - year <= 5:
                    has_dated = True
                else:
                    has_dated = True
            else:
                has_no_date = True
        except Exception:
            has_no_date = True

    if has_recent:
        return 15, ["Evidence is current within the preferred recency window (+15 pts)."]
    elif has_dated:
        return 10, ["Evidence is moderately dated (2-5 years old) (-5 pts)."]
    elif has_no_date:
        return 8, ["Source publication date could not be strictly confirmed (-7 pts)."]
    else:
        return 5, ["Outdated source material (-10 pts)."]


def assess_contradiction_handling(
    sources: List[EvidenceItem],
    has_conflicts: bool = False,
    conflict_resolved: bool = True
) -> Tuple[int, List[str]]:
    """
    Score contradiction handling (0-10 points).
    """
    if has_conflicts and not conflict_resolved:
        return 2, ["Unresolved contradiction identified between sources (-8 pts)."]
    elif has_conflicts and conflict_resolved:
        return 10, ["Conflicting evidence was surfaced, analyzed, and explicitly resolved (+10 pts)."]
    elif len(sources) >= 2:
        return 10, ["No contradictory evidence found across multiple sources (+10 pts)."]
    else:
        return 7, ["Single source examined; limited adversarial stress-testing (-3 pts)."]


def score_claim(
    statement: str,
    sources: List[EvidenceItem],
    has_conflicts: bool = False,
    conflict_resolved: bool = True
) -> ClaimRecord:
    """
    Calculates deterministic rubric score for a single factual claim record.
    """
    auth_score, auth_notes = assess_source_authority(sources)
    corrob_score, corrob_notes = assess_independent_corroboration(sources)
    relevance_score, relevance_notes = assess_direct_relevance(statement, sources)
    recency_score, recency_notes = assess_recency(sources)
    contradiction_score, contradiction_notes = assess_contradiction_handling(
        sources, has_conflicts=has_conflicts, conflict_resolved=conflict_resolved
    )

    total_score = auth_score + corrob_score + relevance_score + recency_score + contradiction_score
    total_score = max(0, min(100, total_score))

    breakdown = {
        "source_authority": auth_score,
        "independent_corroboration": corrob_score,
        "direct_relevance": relevance_score,
        "recency": recency_score,
        "contradiction_handling": contradiction_score
    }

    limitations = []
    for notes in [auth_notes, corrob_notes, relevance_notes, recency_notes, contradiction_notes]:
        for n in notes:
            if "-" in n:
                limitations.append(n)

    # Determine status & relationship
    if has_conflicts and not conflict_resolved:
        status = ClaimStatus.DISPUTED
        relationship = ClaimRelationship.CONTRADICTS
    elif total_score >= 75:
        status = ClaimStatus.VERIFIED
        relationship = ClaimRelationship.SUPPORTS
    elif total_score >= 45:
        status = ClaimStatus.PARTIALLY_SUPPORTED
        relationship = ClaimRelationship.PARTIALLY_SUPPORTS
    else:
        status = ClaimStatus.UNVERIFIED
        relationship = ClaimRelationship.DOES_NOT_ADDRESS

    import uuid
    claim_id = f"claim-{uuid.uuid4().hex[:8]}"

    return ClaimRecord(
        claim_id=claim_id,
        statement=statement,
        evidence_sources=sources,
        relationship=relationship,
        source_quality="primary" if auth_score >= 28 else "secondary",
        status=status,
        rubric_score=total_score,
        rubric_breakdown=breakdown,
        limitations=limitations
    )


def compute_aggregate_evidence_strength(claims: List[ClaimRecord]) -> EvidenceStrengthScore:
    """
    Computes an aggregate evidence-strength score and explanation from claim-level records.
    Explicitly labeled as heuristic per Veritas AI blueprint guidelines.
    """
    if not claims:
        return EvidenceStrengthScore(
            overall_score=0,
            label="heuristic",
            verified_claims_count=0,
            partially_supported_count=0,
            disputed_claims_count=0,
            unverified_claims_count=0,
            rubric_breakdown={
                "source_authority": 0.0,
                "independent_corroboration": 0.0,
                "direct_relevance": 0.0,
                "recency": 0.0,
                "contradiction_handling": 0.0
            },
            explanation="No factual claims could be extracted or verified from the response.",
            deductions=["No verifiable claims identified."]
        )

    verified = sum(1 for c in claims if c.status == ClaimStatus.VERIFIED)
    partially = sum(1 for c in claims if c.status == ClaimStatus.PARTIALLY_SUPPORTED)
    disputed = sum(1 for c in claims if c.status == ClaimStatus.DISPUTED)
    unverified = sum(1 for c in claims if c.status == ClaimStatus.UNVERIFIED)

    # Weighted scoring: Disputed claims heavily penalize overall confidence
    scores = [c.rubric_score for c in claims]
    avg_score = sum(scores) / len(scores)

    # Penalize if any claims are disputed or unverified
    disputed_penalty = disputed * 15
    unverified_penalty = unverified * 10
    final_score = int(max(0, min(100, avg_score - disputed_penalty - unverified_penalty)))

    # Compute criterion averages
    avg_breakdown = {
        "source_authority": round(sum(c.rubric_breakdown.get("source_authority", 0) for c in claims) / len(claims), 1),
        "independent_corroboration": round(sum(c.rubric_breakdown.get("independent_corroboration", 0) for c in claims) / len(claims), 1),
        "direct_relevance": round(sum(c.rubric_breakdown.get("direct_relevance", 0) for c in claims) / len(claims), 1),
        "recency": round(sum(c.rubric_breakdown.get("recency", 0) for c in claims) / len(claims), 1),
        "contradiction_handling": round(sum(c.rubric_breakdown.get("contradiction_handling", 0) for c in claims) / len(claims), 1)
    }

    # Aggregate deductions
    deductions = []
    if disputed > 0:
        deductions.append(f"{disputed} claim(s) contain conflicting or disputed evidence (-{disputed_penalty} pts).")
    if unverified > 0:
        deductions.append(f"{unverified} claim(s) lack sufficient verifiable evidence (-{unverified_penalty} pts).")
    for c in claims:
        for lim in c.limitations:
            if lim not in deductions:
                deductions.append(lim)

    explanation = (
        f"Evidence strength: {final_score}/100 (heuristic). "
        f"{verified} of {len(claims)} claim(s) verified; "
        f"{partially} partially supported; "
        f"{disputed} disputed. "
        "This score describes the available evidence based on explicit rubric criteria, "
        "not a statistical probability of correctness."
    )

    return EvidenceStrengthScore(
        overall_score=final_score,
        label="heuristic",
        verified_claims_count=verified,
        partially_supported_count=partially,
        disputed_claims_count=disputed,
        unverified_claims_count=unverified,
        rubric_breakdown=avg_breakdown,
        explanation=explanation,
        deductions=deductions
    )
