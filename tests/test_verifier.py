"""Tests for Person 3 - Evidence Collection & Claim Verification (app/services/verifier.py)."""
from app.schemas import EvidenceItem, ClaimStatus, ClaimRelationship
from app.services.verifier import (
    extract_claims,
    extract_claims_with_spans,
    detect_conflicts,
    find_conflicts,
    verify_evidence_and_claims,
    build_verification_summary,
)


def ev(title, url, passage, authority="high", date="2026-03-01", source_type="web"):
    return EvidenceItem(source_title=title, url_or_id=url, passage=passage,
                        authority_level=authority, publication_date=date, source_type=source_type)


SOLAR_30 = ev("NREL", "https://www.nrel.gov/solar", "Utility-scale solar installations increased 30% year-over-year in 2024.")
SOLAR_12 = ev("Reuters", "https://www.reuters.com/solar", "Utility-scale solar capacity grew 12 percent in 2024, federal data shows.")


# --- Bullet 1: extract individual factual claims -------------------------------------------
def test_extract_claims_keeps_facts_and_drops_noise():
    answer = (
        "## Findings\n"
        "Here is a summary of the findings:\n"
        "- Sodium-ion batteries lower raw material costs by about 30% compared with lithium-ion [1].\n"
        "- CATL began mass production of sodium-ion cells in 2023.\n"
        "Do you want more detail?\n"
        "I think this is a great technology. You should consider pilot projects.\n"
    )
    claims = extract_claims(answer)
    assert len(claims) == 2
    assert any("30%" in c for c in claims)
    assert any("CATL" in c for c in claims)
    assert all("[1]" not in c and "?" not in c for c in claims)


def test_extract_claims_records_answer_span_and_dedupes():
    text = "Solar capacity grew 12 percent in 2024. Solar capacity grew 12 percent in 2024."
    pairs = extract_claims_with_spans(text)
    assert len(pairs) == 1
    assert pairs[0][1].startswith("Solar capacity")


def test_extract_claims_ignores_placeholder_answers():
    assert extract_claims("No evidence found. Configure Tavily or upload relevant documents.") == []
    assert extract_claims("") == []


def test_extract_claims_handles_decimals_and_abbreviations():
    claims = extract_claims("The U.S. grid added 3.5 GW of storage in 2024, e.g. in Texas and California.")
    assert len(claims) == 1 and "3.5 GW" in claims[0]


# --- Bullets 2 & 3: find supporting evidence and match claims to sources -----------------------
def test_supported_claim_is_matched_to_its_passage_and_verified():
    sources = [
        ev("NREL", "https://www.nrel.gov/sodium-ion.html", "Sodium-ion batteries show lower material costs than lithium-ion equivalents.", date="2025-04-12"),
        ev("Bloomberg", "https://www.bloomberg.com/news/sodium", "Material costs for sodium-ion batteries are significantly lower than lithium-ion.", date="2025-05-18"),
    ]
    claims, score = verify_evidence_and_claims(
        ["Sodium-ion batteries show lower material costs than lithium-ion"], sources, [])
    c = claims[0]
    assert c.status == ClaimStatus.VERIFIED
    assert len(c.evidence_matches) == 2
    assert all(m.stance == ClaimRelationship.SUPPORTS for m in c.evidence_matches)
    assert "lower" in c.evidence_matches[0].supporting_passage.lower()
    assert score.overall_score >= 80


def test_irrelevant_source_is_not_attached_to_claim():
    claims, _ = verify_evidence_and_claims(
        ["Sodium-ion batteries show lower material costs than lithium-ion"],
        [ev("Hydro", "https://www.energy.gov/hydro", "Hydroelectric turbines in Norway generate most national power.")], [])
    assert claims[0].evidence_matches == []
    assert claims[0].evidence_sources == []


def test_agent_generated_analysis_is_not_counted_as_independent_evidence():
    agent = ev("Domain Analysis", "agent://domain-analysis",
               "Sodium-ion batteries show lower material costs than lithium-ion.", source_type="analysis")
    claims, _ = verify_evidence_and_claims(["Sodium-ion batteries show lower material costs than lithium-ion"], [agent], [])
    assert claims[0].status == ClaimStatus.UNVERIFIED


# --- Bullet 4: unsupported / partially supported claims ----------------------------------------
def test_unsupported_claim_is_flagged_unverified():
    claims, score = verify_evidence_and_claims(
        ["Hydroelectric turbines in Norway generate 90% of national power"], [SOLAR_30], [])
    c = claims[0]
    assert c.status == ClaimStatus.UNVERIFIED
    assert c.relationship == ClaimRelationship.DOES_NOT_ADDRESS
    assert c.unsupported_parts
    assert score.unverified_claims_count == 1


def test_partially_supported_when_number_not_in_sources():
    src = ev("NREL", "https://www.nrel.gov/solar", "Utility-scale solar installations increased significantly year-over-year in 2024.")
    claims, _ = verify_evidence_and_claims(["Utility-scale solar installations increased 30% in 2024"], [src], [])
    c = claims[0]
    assert c.status == ClaimStatus.PARTIALLY_SUPPORTED
    assert any("30%" in p for p in c.unsupported_parts)
    assert c.rubric_score <= 74


# --- Bullet 5: conflicting information ------------------------------------------------------
def test_numeric_conflict_between_claim_and_source_is_disputed():
    claims, score = verify_evidence_and_claims(
        ["Utility-scale solar installations increased 30% in 2024"], [SOLAR_30, SOLAR_12], [])
    c = claims[0]
    assert c.status == ClaimStatus.DISPUTED
    assert any(x.conflict_type == "numeric_mismatch" and not x.resolved for x in c.conflicts)
    assert c.rubric_score <= 59
    assert score.disputed_claims_count == 1


def test_negation_conflict_between_sources():
    a = ev("IEEE", "https://ieee.org/a", "Sodium-ion batteries are safe for grid-scale storage deployments.")
    b = ev("Nature", "https://nature.com/b", "Sodium-ion batteries are not safe for grid-scale storage deployments.")
    has, resolved = detect_conflicts("Sodium-ion batteries are safe for grid-scale storage deployments", [a, b], [])
    assert has is True and resolved is False


def test_direction_conflict_detected():
    src = ev("WB", "https://worldbank.org/x", "Battery storage costs decreased sharply across the grid market.")
    conflicts = find_conflicts("Battery storage costs increased sharply across the grid market", [src], [])
    assert any(c.conflict_type == "direction" for c in conflicts)


def test_conflict_between_two_sources_even_when_claim_is_generic():
    claims, _ = verify_evidence_and_claims(
        ["Utility-scale solar installations grew in 2024"], [SOLAR_30, SOLAR_12], [])
    assert any(c.conflict_type == "source_vs_source" for c in claims[0].conflicts)


def test_conflict_resolved_when_many_independent_sources_outweigh_one():
    third = ev("Bloomberg", "https://www.bloomberg.com/solar", "Utility-scale solar installations increased 30% in 2024, Bloomberg analysis found.")
    claims, _ = verify_evidence_and_claims(
        ["Utility-scale solar installations increased 30% in 2024"], [SOLAR_30, third, SOLAR_12], [])
    conflict = [c for c in claims[0].conflicts if c.conflict_type == "numeric_mismatch"][0]
    assert conflict.resolved is True


def test_no_conflict_when_sources_agree():
    a = ev("NREL", "https://www.nrel.gov/solar", "Solar installations increased 30% in 2024.")
    b = ev("Reuters", "https://www.reuters.com/solar", "Solar installations grew 30 percent in 2024.")
    has, _ = detect_conflicts("Solar installations increased 30% in 2024", [a, b], [])
    assert has is False


def test_counter_analysis_objection_is_reported():
    objections = ["However, utility-scale solar installations growth figures may be overstated."]
    conflicts = find_conflicts("Utility-scale solar installations increased 30% in 2024", [SOLAR_30], objections)
    assert any(c.conflict_type == "counter_analysis" for c in conflicts)


# --- Bullet 6: claim-level results handed to Person 4 ---------------------------------------
def test_full_answer_yields_claim_level_records_with_spans_and_summary():
    answer = ("Sodium-ion batteries rely on abundant sodium, which lowers raw material costs compared with lithium-ion. "
              "Cycle life exceeds 6,000 cycles at Tesla Megapack sites.")
    sources = [
        ev("NREL", "https://www.nrel.gov/si", "Sodium-ion batteries rely on abundant sodium, which lowers raw material costs compared with lithium-ion."),
        ev("DOE", "https://energy.gov/si", "Sodium-ion chemistry uses abundant sodium and reduces raw material costs relative to lithium-ion batteries."),
    ]
    claims, score = verify_evidence_and_claims(answer, sources, [])
    assert len(claims) == 2
    assert claims[0].status == ClaimStatus.VERIFIED and claims[0].source_answer_span
    assert claims[1].status == ClaimStatus.UNVERIFIED
    summary = build_verification_summary(claims)
    assert summary["total_claims"] == 2 and len(summary["unverified"]) == 1
    assert score.label == "heuristic"
    # existing downstream fields still populated
    assert claims[0].rubric_breakdown and claims[0].claim_id.startswith("claim-")


def test_claims_derived_from_evidence_are_never_fully_verified():
    claims, _ = verify_evidence_and_claims("", [SOLAR_30, SOLAR_12], [])
    assert claims and all(c.status != ClaimStatus.VERIFIED for c in claims)
    assert all(any("derived" in l.lower() for l in c.limitations) for c in claims)
