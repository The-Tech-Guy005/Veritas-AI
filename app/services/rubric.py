"""
Deterministic Evidence Verification Rubric
Implements the 5-criterion evidence strength rubric specified in Veritas AI Blueprint:
1. Source Authority          (Max 30)
2. Independent Corroboration (Max 25)
3. Direct Relevance          (Max 20)
4. Recency                   (Max 15)
5. Contradiction Handling    (Max 10)
Total: 100 points

Bug-fixes applied (v2):
  FIX-1  Relevance gate    – relevance score <= 4 forces UNVERIFIED; <= 8 blocks VERIFIED.
  FIX-2  Authority match   – exact domain / TLD matching; .org substring and "kb" substring
                             false-positives removed.  tkbblog.com is never treated as KB.
  FIX-3  Corroboration     – www-normalised canonical domains only; KB chunks from the same
                             document collapse to one origin; www.x.com == x.com.
  FIX-4  Recency           – per-source recency score, authority-weighted average so one
                             cherry-picked recent source cannot give full credit.
                             The previously unreachable "outdated > 10 yr" branch is now live.
  FIX-5  Critical claims   – disputed / high-weight claims get 2× weight; a critical disputed
                             claim hard-caps the overall at 59 (the dispute ceiling used throughout
                             the pipeline), so it cannot be hidden by several verified minor ones.
  FIX-6  Double penalty    – unverified claims already score low; they are no longer penalised
                             a second time in the aggregate.
"""

import re
import uuid
import datetime
from typing import Dict, List, Optional, Tuple

from app.schemas import (
    ClaimRecord, ClaimRelationship, ClaimStatus,
    EvidenceItem, EvidenceStrengthScore,
    CriterionDeduction, ClaimDeductionDetail,
)

# Canonical maximum points per criterion defined by the 5-criterion Veritas rubric
CRITERION_MAX_POINTS: Dict[str, int] = {
    "source_authority": 30,
    "independent_corroboration": 25,
    "direct_relevance": 20,
    "recency": 15,
    "contradiction_handling": 10,
}

# ===========================================================================
# FIX-2  Domain-level authority matching
# ===========================================================================

# Exact registrable domains (after www. stripping) that confer HIGH authority.
# Keeping this as a whitelist prevents any .org / .com site from being promoted.
HIGH_AUTHORITY_DOMAINS: frozenset = frozenset({
    # Science / research
    "ieee.org", "nature.com", "sciencedirect.com", "arxiv.org",
    "pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov", "scholar.google.com",
    # Government / intergovernmental
    "who.int", "un.org", "worldbank.org", "imf.org",
    "nasa.gov", "whitehouse.gov", "nih.gov",
    # High-quality wire / factual journalism
    "reuters.com", "bloomberg.com", "apnews.com", "bbc.co.uk",
})

# TLDs that unconditionally confer HIGH authority (government, military, education).
HIGH_AUTHORITY_TLDS: frozenset = frozenset({".gov", ".edu", ".mil"})

# Exact domains treated as MEDIUM authority.
MEDIUM_AUTHORITY_DOMAINS: frozenset = frozenset({
    "techcrunch.com", "bbc.com", "forbes.com", "wsj.com", "ft.com",
    "economist.com", "theguardian.com", "nytimes.com", "washingtonpost.com",
    "theatlantic.com", "wired.com", "arstechnica.com", "cnbc.com",
})

# TLDs treated as MEDIUM (better than unknown but not authoritative by default).
# NOTE: .org is intentionally medium here – not every .org is authoritative.
#       Well-known .org authoritative domains are captured by HIGH_AUTHORITY_DOMAINS.
MEDIUM_AUTHORITY_TLDS: frozenset = frozenset({".org", ".com", ".net", ".io"})


def _extract_domain(url_or_id: str) -> str:
    """
    Return the canonical host for a URL: lowercase, scheme stripped,
    www[N]. prefix stripped, port stripped, path stripped.
    Returns the raw string unchanged when it is not a URL-shaped string.
    """
    u = (url_or_id or "").lower().strip()
    # Strip scheme (http://, https://, kb://, ftp://, …)
    u = re.sub(r"^[a-z][a-z0-9+\-.]*://", "", u)
    # Strip userinfo (user:pass@host)
    u = re.sub(r"^[^@/]+@", "", u)
    # Host is everything before the first /, ?, or #
    host = re.split(r"[/?#]", u)[0]
    # Strip port  (host:8080)
    if ":" in host:
        host = host.rsplit(":", 1)[0]
    # Normalise www / www2 / www3 prefix
    host = re.sub(r"^www\d*\.", "", host)
    return host


def _tld(domain: str) -> str:
    """Return the TLD label of a domain, e.g. 'example.gov' → '.gov'."""
    parts = domain.rsplit(".", 1)
    return f".{parts[-1]}" if len(parts) > 1 else ""


def _authority_tier(src: EvidenceItem) -> str:
    """
    Returns 'high', 'kb', 'medium', or 'low' for one source.
    Uses exact domain / TLD matching – never raw substring search.

    Priority order:
      1. Explicit knowledge-base markers (source_type or kb:// URL)
      2. Explicit authority_level == 'high' field override
      3. URL-based domain / TLD lookup
      4. Explicit authority_level == 'low' field override
      5. Default → 'medium'
    """
    # 1. Explicit knowledge-base markers (source_type wins before anything else)
    if src.source_type == "knowledge_base":
        return "kb"
    u = src.url_or_id or ""
    u_lower = u.lower()
    if u_lower.startswith("kb://") or u_lower.startswith("internal_kb"):
        return "kb"

    # 2. Explicit 'high' caller override
    if src.authority_level == "high":
        return "high"

    # 3. URL-based domain matching (only when the value looks like a URL)
    if "://" in u or u_lower.startswith("http"):
        domain = _extract_domain(u)
        tld = _tld(domain)
        if tld in HIGH_AUTHORITY_TLDS or domain in HIGH_AUTHORITY_DOMAINS:
            return "high"
        if domain in MEDIUM_AUTHORITY_DOMAINS or tld in MEDIUM_AUTHORITY_TLDS:
            return "medium"
        # Has a recognisable domain structure but not in any list
        return "low"

    # 4. Explicit 'low' caller override for non-URL identifiers
    if src.authority_level == "low":
        return "low"

    # 5. Default for bare IDs / filenames with no explicit level
    return "medium"


_TIER_SCORE: Dict[str, int] = {"high": 30, "kb": 28, "medium": 20, "low": 12}
_TIER_ORDER: List[str]      = ["high", "kb", "medium", "low"]


# ===========================================================================
# Criterion 1 – Source Authority  (0-30)
# ===========================================================================

def assess_source_authority(sources: List[EvidenceItem]) -> Tuple[int, List[str]]:
    """Score source authority (0-30 points).  Takes the best tier across sources."""
    if not sources:
        return 0, ["No sources provided (-30 pts)."]

    best_tier = "low"
    for src in sources:
        t = _authority_tier(src)
        if _TIER_ORDER.index(t) < _TIER_ORDER.index(best_tier):
            best_tier = t

    score = _TIER_SCORE[best_tier]
    if best_tier == "high":
        note = "High-authority authoritative source verified (+30 pts)."
    elif best_tier == "kb":
        note = "Verified internal team knowledge-base document cited (+28 pts)."
    elif best_tier == "medium":
        note = ("Secondary or reputable industry source cited; lacks primary "
                "peer-reviewed/official authority (-10 pts).")
    else:
        note = "Low-authority domain (-18 pts)."

    return score, [note]


# ===========================================================================
# FIX-3  Corroboration – distinct canonical domains only  (0-25)
# ===========================================================================

def _corroboration_key(src: EvidenceItem) -> str:
    """
    Canonical key for counting distinct independent sources.
    • KB chunks from the same document collapse to a single key.
    • www.x.com and x.com collapse to the same key (via _extract_domain).
    """
    u = src.url_or_id or ""
    # KB sources: strip scheme and take doc-level ID before the first slash
    if src.source_type == "knowledge_base" or u.lower().startswith("kb://"):
        bare = re.sub(r"^(?:kb://)", "", u.lower())
        return "kb:" + bare.split("/")[0]   # e.g. "kb:doc-abc123"
    # Web / other: canonical domain (www. already stripped)
    domain = _extract_domain(u)
    return domain if domain else u.lower()


def assess_independent_corroboration(sources: List[EvidenceItem]) -> Tuple[int, List[str]]:
    """
    Score independent corroboration (0-25 points).
    Counts only distinct canonical domains / KB document IDs.
    www.x.com and x.com are the same origin; chunks of the same KB doc are one origin.
    """
    if not sources:
        return 0, ["No independent corroboration (-25 pts)."]

    distinct_origins = {_corroboration_key(src) for src in sources}
    count = len(distinct_origins)

    if count >= 3:
        return 25, ["Three or more independent sources corroborate this finding (+25 pts)."]
    elif count == 2:
        return 22, ["Two independent sources corroborate this finding (+22 pts)."]
    elif count == 1:
        return 14, ["Single source cited without independent corroboration (-11 pts)."]
    else:
        return 0, ["No corroborating sources found (-25 pts)."]


# ===========================================================================
# Criterion 3 – Direct Relevance  (0-20)
# ===========================================================================

def assess_direct_relevance(claim: str, sources: List[EvidenceItem]) -> Tuple[int, List[str]]:
    """
    Score direct relevance (0-20 points).
    Evaluates whether cited text passages directly support the specific claim words.
    Scoring bands are unchanged; FIX-1 uses the returned score as a gate in score_claim().
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
        return 8,  ["Cited passage is only tangentially related (-12 pts)."]
    else:
        return 4,  ["Cited evidence does not clearly cover key claim concepts (-16 pts)."]


# ===========================================================================
# FIX-4  Recency – authority-weighted per-source average  (0-15)
# ===========================================================================

def _per_source_recency(date_str: Optional[str], current_year: int) -> int:
    """
    Return a 0-15 recency score for a single source's publication date string.
    All four age tiers are now reachable (the > 10 yr branch was previously dead).
    """
    if not date_str:
        return 8   # undated: moderate penalty
    years = re.findall(r"\b(19\d\d|20\d\d)\b", date_str)
    if not years:
        return 8
    year = int(years[-1])
    age = current_year - year
    if age <= 2:
        return 15   # current
    elif age <= 5:
        return 10   # moderately dated
    elif age <= 10:
        return 5    # dated  (FIX-4: was previously unreachable)
    else:
        return 2    # very old


def assess_recency(sources: List[EvidenceItem]) -> Tuple[int, List[str]]:
    """
    Score recency (0-15 points).

    FIX-4: computes an authority-weighted average of per-source recency scores.
    One cherry-picked recent source can no longer award full credit when the
    majority of supporting evidence is old.
    """
    if not sources:
        return 0, ["Undated source (-15 pts)."]

    current_year = datetime.datetime.now(datetime.timezone.utc).year
    _tier_weight: Dict[str, float] = {"high": 3.0, "kb": 2.5, "medium": 2.0, "low": 1.0}

    weighted_sum = 0.0
    total_weight = 0.0
    for src in sources:
        tier = _authority_tier(src)
        w = _tier_weight.get(tier, 1.0)
        s = _per_source_recency(src.publication_date, current_year)
        weighted_sum += w * s
        total_weight += w

    raw   = weighted_sum / total_weight
    final = max(0, min(15, int(raw + 0.5)))   # standard round-half-up

    if final >= 14:
        note = "Evidence is current within the preferred recency window (+15 pts)."
    elif final >= 9:
        note = "Evidence is moderately dated (2–5 years old) (-5 pts)."
    elif final >= 4:
        note = "Source material is dated (5–10 years old) (-10 pts)."
    else:
        note = "Source material is very old or largely undated (-13 pts)."

    return final, [note]


# ===========================================================================
# Criterion 5 – Contradiction Handling  (0-10)
# ===========================================================================

def assess_contradiction_handling(
    sources: List[EvidenceItem],
    has_conflicts: bool = False,
    conflict_resolved: bool = True,
) -> Tuple[int, List[str]]:
    """Score contradiction handling (0-10 points)."""
    if has_conflicts and not conflict_resolved:
        return 2,  ["Unresolved contradiction identified between sources (-8 pts)."]
    elif has_conflicts and conflict_resolved:
        return 10, ["Conflicting evidence was surfaced, analyzed, and explicitly resolved (+10 pts)."]
    elif len(sources) >= 2:
        return 10, ["No contradictory evidence found across multiple sources (+10 pts)."]
    else:
        return 7,  ["Single source examined; limited adversarial stress-testing (-3 pts)."]


# ===========================================================================
# FIX-1  score_claim – relevance gate
# ===========================================================================

def score_claim(
    statement: str,
    sources: List[EvidenceItem],
    has_conflicts: bool = False,
    conflict_resolved: bool = True,
    is_critical: bool = False,
) -> ClaimRecord:
    """
    Calculates deterministic rubric score for a single factual claim record.

    FIX-1  Relevance gate:
      relevance_score <= 4  → passage does not address the claim at all →
                               status forced to UNVERIFIED regardless of total score.
      relevance_score <= 8  → passage is only tangentially related →
                               VERIFIED blocked; at best PARTIALLY_SUPPORTED.
    This prevents a claim from reaching VERIFIED with a high authority + corroboration
    score when the cited passage does not actually support the specific claim.
    """
    auth_score,          auth_notes          = assess_source_authority(sources)
    corrob_score,        corrob_notes        = assess_independent_corroboration(sources)
    relevance_score,     relevance_notes     = assess_direct_relevance(statement, sources)
    recency_score,       recency_notes       = assess_recency(sources)
    contradiction_score, contradiction_notes = assess_contradiction_handling(
        sources, has_conflicts=has_conflicts, conflict_resolved=conflict_resolved,
    )

    total_score = max(0, min(100,
        auth_score + corrob_score + relevance_score + recency_score + contradiction_score
    ))

    breakdown: Dict[str, int] = {
        "source_authority":          auth_score,
        "independent_corroboration": corrob_score,
        "direct_relevance":          relevance_score,
        "recency":                   recency_score,
        "contradiction_handling":    contradiction_score,
    }

    # Per-criterion points lost & structured deductions (Criterion 7)
    criteria_data = [
        ("source_authority", 30, auth_score, auth_notes),
        ("independent_corroboration", 25, corrob_score, corrob_notes),
        ("direct_relevance", 20, relevance_score, relevance_notes),
        ("recency", 15, recency_score, recency_notes),
        ("contradiction_handling", 10, contradiction_score, contradiction_notes),
    ]

    deduction_items: List[CriterionDeduction] = []
    criterion_points_lost: Dict[str, int] = {}
    for crit, max_pts, score, notes in criteria_data:
        lost = max(0, max_pts - score)
        criterion_points_lost[crit] = lost
        if lost > 0:
            note_str = ""
            for n in notes:
                if "(-" in n:
                    note_str = n
                    break
            if not note_str and notes:
                note_str = notes[0]
            deduction_items.append(
                CriterionDeduction(
                    criterion=crit,
                    points_lost=lost,
                    max_points=max_pts,
                    reason=note_str or f"{crit.replace('_', ' ').title()} points lost"
                )
            )

    points_lost = sum(criterion_points_lost.values())

    # Collect limitation notes (only lines that contain a deduction marker)
    limitations: List[str] = []
    for notes in [auth_notes, corrob_notes, relevance_notes, recency_notes, contradiction_notes]:
        for n in notes:
            if "(-" in n:
                limitations.append(n)

    # ------------------------------------------------------------------
    # FIX-1: Relevance gate – evaluated before the score-threshold ladder
    # ------------------------------------------------------------------
    if has_conflicts and not conflict_resolved:
        # Disputed takes absolute priority
        status       = ClaimStatus.DISPUTED
        relationship = ClaimRelationship.CONTRADICTS

    elif relevance_score <= 4:
        # Evidence does not address the claim at all → cannot be better than UNVERIFIED
        status       = ClaimStatus.UNVERIFIED
        relationship = ClaimRelationship.DOES_NOT_ADDRESS
        limitations.append(
            "Relevance gate: evidence passage does not address this claim (-16 pts); "
            "VERIFIED and PARTIALLY_SUPPORTED statuses blocked."
        )

    elif relevance_score <= 8:
        # Tangential evidence → cannot be better than PARTIALLY_SUPPORTED
        if total_score >= 45:
            status       = ClaimStatus.PARTIALLY_SUPPORTED
            relationship = ClaimRelationship.PARTIALLY_SUPPORTS
        else:
            status       = ClaimStatus.UNVERIFIED
            relationship = ClaimRelationship.DOES_NOT_ADDRESS
        limitations.append(
            "Relevance gate: evidence is only tangentially related (-12 pts); "
            "VERIFIED status blocked."
        )

    elif total_score >= 75:
        status       = ClaimStatus.VERIFIED
        relationship = ClaimRelationship.SUPPORTS

    elif total_score >= 45:
        status       = ClaimStatus.PARTIALLY_SUPPORTED
        relationship = ClaimRelationship.PARTIALLY_SUPPORTS

    else:
        status       = ClaimStatus.UNVERIFIED
        relationship = ClaimRelationship.DOES_NOT_ADDRESS

    claim_id = f"claim-{uuid.uuid4().hex[:8]}"
    verification_notes: List[str] = []
    if is_critical:
        verification_notes.append("__is_critical__")

    return ClaimRecord(
        claim_id=claim_id,
        statement=statement,
        evidence_sources=sources,
        relationship=relationship,
        source_quality="primary" if auth_score >= 28 else "secondary",
        status=status,
        rubric_score=total_score,
        rubric_breakdown=breakdown,
        limitations=limitations,
        verification_notes=verification_notes,
        is_critical=is_critical,
        points_lost=points_lost,
        criterion_points_lost=criterion_points_lost,
        deduction_items=deduction_items,
    )


# ===========================================================================
# FIX-5 & FIX-6  Aggregate evidence-strength score
# ===========================================================================

def compute_aggregate_evidence_strength(claims: List[ClaimRecord]) -> EvidenceStrengthScore:
    """
    Computes an aggregate evidence-strength score and explanation from claim-level records.
    Explicitly labeled as heuristic per Veritas AI blueprint guidelines.

    FIX-5  Critical-claim weighting:
      A claim is "critical" when explicitly flagged as critical or when disputed with substantial
      evidence (rubric_score >= 70 or >= median). Critical claims receive 2x weight.
      If any critical claim is disputed or unverified, the overall is hard-capped at 59.

    FIX-6  No double-penalty for unverified claims:
      Unverified claims already score low through the rubric criteria. Subtracting them
      again from the aggregate score was double-counting the same deficiency.
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
                "source_authority":          0.0,
                "independent_corroboration": 0.0,
                "direct_relevance":          0.0,
                "recency":                   0.0,
                "contradiction_handling":    0.0,
            },
            explanation="No factual claims could be extracted or verified from the response.",
            deductions=["No verifiable claims identified."],
            points_lost_by_criterion={
                "source_authority":          30.0,
                "independent_corroboration": 25.0,
                "direct_relevance":          20.0,
                "recency":                   15.0,
                "contradiction_handling":    10.0,
            },
            claim_deductions=[],
        )

    verified   = sum(1 for c in claims if c.status == ClaimStatus.VERIFIED)
    partially  = sum(1 for c in claims if c.status == ClaimStatus.PARTIALLY_SUPPORTED)
    disputed   = sum(1 for c in claims if c.status == ClaimStatus.DISPUTED)
    unverified = sum(1 for c in claims if c.status == ClaimStatus.UNVERIFIED)

    # --- FIX-5: Critical-claim identification --------------------------------
    scores       = [c.rubric_score for c in claims]
    median_score = sorted(scores)[len(scores) // 2]

    total_w      = 0.0
    weighted_sum = 0.0
    for c in claims:
        is_crit = (
            getattr(c, "is_critical", False)
            or ("__is_critical__" in getattr(c, "verification_notes", []))
            or (c.status == ClaimStatus.DISPUTED and (c.rubric_score >= 70 or c.rubric_score >= median_score or len(claims) <= 2))
        )
        w = 2.0 if is_crit else 1.0
        weighted_sum += w * c.rubric_score
        total_w += w

    base_score = weighted_sum / total_w if total_w else 0.0

    # Hard cap at 59: a critical disputed/unverified claim means overall cannot look "good"
    critical_disputed = [
        c for c in claims
        if (c.status == ClaimStatus.DISPUTED) and (
            getattr(c, "is_critical", False)
            or ("__is_critical__" in getattr(c, "verification_notes", []))
            or c.rubric_score >= 70
            or c.rubric_score >= median_score
            or len(claims) <= 2
        )
    ]
    critical_unverified = [
        c for c in claims
        if (c.status == ClaimStatus.UNVERIFIED) and (
            getattr(c, "is_critical", False)
            or ("__is_critical__" in getattr(c, "verification_notes", []))
        )
    ]
    if critical_disputed or critical_unverified:
        base_score = min(base_score, 59.0)

    # --- FIX-6: No unverified double-penalty ---------------------------------
    disputed_adjustment = disputed * 5
    final_score = int(max(0, min(100, base_score - disputed_adjustment)))

    # Criterion averages for the breakdown table
    avg_breakdown: Dict[str, float] = {
        k: round(
            sum(c.rubric_breakdown.get(k, 0) for c in claims) / len(claims), 1
        )
        for k in (
            "source_authority", "independent_corroboration",
            "direct_relevance", "recency", "contradiction_handling",
        )
    }

    # Per-criterion points lost data (Criterion 7)
    points_lost_by_criterion: Dict[str, float] = {
        k: round(max(0.0, CRITERION_MAX_POINTS[k] - avg_breakdown.get(k, 0.0)), 1)
        for k in (
            "source_authority", "independent_corroboration",
            "direct_relevance", "recency", "contradiction_handling",
        )
    }

    # Per-claim deduction detail objects (Criterion 7)
    claim_deductions = [
        ClaimDeductionDetail(
            claim_id=c.claim_id,
            statement=c.statement,
            total_points_lost=getattr(c, "points_lost", 100 - c.rubric_score),
            criterion_deductions=getattr(c, "deduction_items", []),
        )
        for c in claims
    ]

    # Descriptive and linked deductions
    deductions: List[str] = []
    if critical_disputed:
        deductions.append(
            f"{len(critical_disputed)} critical claim(s) contain unresolved conflicting "
            f"evidence (overall score capped at 59)."
        )
    elif critical_unverified:
        deductions.append(
            f"{len(critical_unverified)} critical claim(s) lack verifiable evidence "
            f"(overall score capped at 59)."
        )
    elif disputed > 0:
        deductions.append(
            f"{disputed} claim(s) contain conflicting or disputed evidence "
            f"(-{disputed_adjustment} pts)."
        )

    # FIX-6: unverified noted descriptively – no numeric deduction added
    if unverified > 0:
        deductions.append(
            f"{unverified} claim(s) lack sufficient verifiable evidence "
            f"(already reflected in their individual rubric scores; no additional deduction)."
        )

    # Per-claim linked deduction items
    for c in claims:
        c_items = getattr(c, "deduction_items", [])
        for d in c_items:
            if d.points_lost > 0:
                linked_msg = f"[{c.claim_id}] {d.criterion.replace('_', ' ').title()}: {d.reason} (-{d.points_lost} pts)"
                if linked_msg not in deductions:
                    deductions.append(linked_msg)

    explanation = (
        f"Evidence strength: {final_score}/100 (heuristic). "
        f"{verified} of {len(claims)} claim(s) verified; "
        f"{partially} partially supported; "
        f"{disputed} disputed; "
        f"{unverified} unverified. "
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
        deductions=deductions,
        points_lost_by_criterion=points_lost_by_criterion,
        claim_deductions=claim_deductions,
    )
