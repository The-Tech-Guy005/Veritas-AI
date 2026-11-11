import pytest
from app.services.rubric import (
    assess_source_authority,
    assess_independent_corroboration,
    assess_direct_relevance,
    assess_recency,
    assess_contradiction_handling,
    score_claim,
    compute_aggregate_evidence_strength
)
from app.schemas import EvidenceItem, ClaimStatus, ClaimRelationship

def test_source_authority_scoring():
    gov_source = [EvidenceItem(
        source_title="NREL Report",
        url_or_id="https://www.nrel.gov/research/pv.html",
        source_type="web",
        passage="Solar efficiency reached 24 percent.",
        authority_level="high"
    )]
    score, notes = assess_source_authority(gov_source)
    assert score == 30
    assert any("High-authority" in n for n in notes)

    blog_source = [EvidenceItem(
        source_title="Random Blog",
        url_or_id="https://myenergyblog.xyz/post",
        source_type="web",
        passage="Solar panels are cool.",
        authority_level="low"
    )]
    score, notes = assess_source_authority(blog_source)
    assert score <= 15

def test_corroboration_scoring():
    sources_multi = [
        EvidenceItem(source_title="S1", url_or_id="https://nature.com/articles/1", passage="Fact", authority_level="high"),
        EvidenceItem(source_title="S2", url_or_id="https://reuters.com/energy/1", passage="Fact", authority_level="high"),
        EvidenceItem(source_title="S3", url_or_id="https://bloomberg.com/news/1", passage="Fact", authority_level="high"),
    ]
    score, _ = assess_independent_corroboration(sources_multi)
    assert score == 25

    single_source = [sources_multi[0]]
    score, _ = assess_independent_corroboration(single_source)
    assert score == 14

def test_direct_relevance():
    sources = [EvidenceItem(
        source_title="Energy Storage",
        url_or_id="https://nrel.gov/battery",
        passage="Lithium iron phosphate battery density improved significantly in recent testing cycles.",
        authority_level="high"
    )]
    score, _ = assess_direct_relevance("Lithium iron phosphate battery density improved significantly", sources)
    assert score == 20

    score_low, _ = assess_direct_relevance("Hydroelectric turbine operations in Norway", sources)
    assert score_low < 10

def test_score_claim_and_aggregate():
    sources = [
        EvidenceItem(
            source_title="NREL Clean Energy Report",
            url_or_id="https://www.nrel.gov/solar.html",
            publication_date="2025-05-10",
            passage="Utility-scale solar installations increased 30% year-over-year in 2024.",
            authority_level="high"
        ),
        EvidenceItem(
            source_title="Reuters Energy News",
            url_or_id="https://www.reuters.com/business/energy/solar-growth-2024",
            publication_date="2025-06-01",
            passage="Utility-scale solar capacity grew 30 percent according to federal metrics.",
            authority_level="high"
        )
    ]
    claim = score_claim(
        statement="Utility-scale solar installations increased 30% in 2024",
        sources=sources,
        has_conflicts=False,
        conflict_resolved=True
    )
    assert claim.rubric_score >= 80
    assert claim.status == ClaimStatus.VERIFIED
    assert claim.relationship == ClaimRelationship.SUPPORTS

    aggregate = compute_aggregate_evidence_strength([claim])
    assert aggregate.overall_score >= 80
    assert aggregate.label == "heuristic"
    assert aggregate.verified_claims_count == 1
    assert "heuristic" in aggregate.explanation
