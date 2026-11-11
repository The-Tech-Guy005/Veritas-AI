"""
Tests for rubric.py – covers all bug-fixes and enhancements:
  F-1: Relevance gate (low relevance blocks VERIFIED; score <= 4 forces UNVERIFIED)
  F-2: Authority matching (exact domain/TLD matching, tkbblog.com != KB, unknown .org != 30)
  F-3: Corroboration (distinct canonical domains, www stripping, KB chunk collapsing)
  F-4: Recency (outdated branch reachable, very old branch, weighted recency prevents cherry-picking)
  F-5: Critical claims (one key disputed claim cannot be hidden by verified minor ones; capped at 59)
  F-6: No double penalty (unverified claims not penalized twice in aggregate)
  F-7: Deductions & Points Lost (per-claim points_lost, criterion_points_lost, deduction_items,
       aggregate points_lost_by_criterion, and claim_deductions detail)
"""
import datetime
import pytest
from app.services.rubric import (
    assess_source_authority,
    assess_independent_corroboration,
    assess_direct_relevance,
    assess_recency,
    assess_contradiction_handling,
    score_claim,
    compute_aggregate_evidence_strength,
    _extract_domain,
    _corroboration_key,
    _authority_tier,
    _per_source_recency,
    CRITERION_MAX_POINTS,
)
from app.schemas import EvidenceItem, ClaimStatus, ClaimRelationship


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ev(url, passage="fact", authority="medium", source_type="web", date=None):
    return EvidenceItem(
        source_title="T",
        url_or_id=url,
        source_type=source_type,
        authority_level=authority,
        passage=passage,
        publication_date=date,
    )


# ---------------------------------------------------------------------------
# F-2  Authority matching – exact domain / TLD, not substring
# ---------------------------------------------------------------------------

class TestAuthorityMatching:
    def test_gov_tld_is_high(self):
        score, notes = assess_source_authority([_ev("https://nrel.gov/research", authority="medium")])
        assert score == 30

    def test_known_org_domain_is_high(self):
        score, _ = assess_source_authority([_ev("https://www.nature.com/article", authority="medium")])
        assert score == 30

    def test_unknown_org_domain_is_medium_not_high(self):
        # .org alone should NOT grant 30 pts (old bug: any .org → 30)
        score, _ = assess_source_authority([_ev("https://randomnonprofit.org/page", authority="medium")])
        assert score == 20, "Unknown .org should be medium (20), not high (30)"

    def test_kb_in_url_does_not_match_tkbblog(self):
        # tkbblog.com contains "kb" but is NOT a knowledge-base source
        score, _ = assess_source_authority([_ev("https://tkbblog.com/post", authority="low")])
        assert score < 28, "tkbblog.com must not be treated as a knowledge-base source"
        tier = _authority_tier(_ev("https://tkbblog.com/post", authority="low"))
        assert tier != "kb"

    def test_kb_scheme_is_matched(self):
        score, _ = assess_source_authority([
            _ev("kb://doc-42/chunk-3", source_type="knowledge_base", authority="medium")
        ])
        assert score == 28

    def test_knowledge_base_source_type_wins(self):
        score, _ = assess_source_authority([
            _ev("https://anything.com/doc", source_type="knowledge_base", authority="medium")
        ])
        assert score == 28

    def test_explicit_authority_high_wins(self):
        score, _ = assess_source_authority([_ev("https://randomblog.xyz", authority="high")])
        assert score == 30

    def test_extract_domain_strips_www(self):
        assert _extract_domain("https://www.nature.com/article/123") == "nature.com"
        assert _extract_domain("https://www2.example.gov/page") == "example.gov"
        assert _extract_domain("http://nrel.gov/solar") == "nrel.gov"
        assert _extract_domain("tkbblog.com/post") == "tkbblog.com"


# ---------------------------------------------------------------------------
# F-3  Corroboration – distinct canonical domains
# ---------------------------------------------------------------------------

class TestCorroboration:
    def test_www_and_bare_same_domain_count_once(self):
        sources = [
            _ev("https://nature.com/a"),
            _ev("https://www.nature.com/b"),
        ]
        score, _ = assess_independent_corroboration(sources)
        assert score == 14, "www.nature.com and nature.com must count as one domain"

    def test_three_distinct_domains_get_25(self):
        sources = [
            _ev("https://nature.com/a"),
            _ev("https://reuters.com/b"),
            _ev("https://bloomberg.com/c"),
        ]
        score, _ = assess_independent_corroboration(sources)
        assert score == 25

    def test_kb_chunks_same_doc_count_once(self):
        sources = [
            _ev("kb://doc-42/chunk-1", source_type="knowledge_base"),
            _ev("kb://doc-42/chunk-7", source_type="knowledge_base"),
            _ev("kb://doc-42/chunk-99", source_type="knowledge_base"),
        ]
        score, _ = assess_independent_corroboration(sources)
        assert score == 14, "Three chunks of the same KB doc should count as 1 source"

    def test_different_kb_docs_count_separately(self):
        sources = [
            _ev("kb://doc-1/chunk-1", source_type="knowledge_base"),
            _ev("kb://doc-2/chunk-1", source_type="knowledge_base"),
        ]
        score, _ = assess_independent_corroboration(sources)
        assert score == 22

    def test_corroboration_key_www_normalization(self):
        s1 = _ev("https://www.example.com/a")
        s2 = _ev("https://example.com/b")
        assert _corroboration_key(s1) == _corroboration_key(s2)


# ---------------------------------------------------------------------------
# F-1  Relevance gate
# ---------------------------------------------------------------------------

class TestRelevanceGate:
    def test_low_relevance_blocks_verified(self):
        # High authority + high corroboration, but irrelevant passage (score 8/20)
        sources = [
            EvidenceItem(
                source_title="NREL",
                url_or_id="https://nrel.gov/solar",
                source_type="web",
                authority_level="high",
                passage="Hydroelectric turbines in Norway produce significant power.",
                publication_date="2025-01-01",
            ),
            EvidenceItem(
                source_title="Reuters",
                url_or_id="https://reuters.com/energy",
                source_type="web",
                authority_level="high",
                passage="Norwegian water dams were upgraded last year.",
                publication_date="2025-03-01",
            ),
        ]
        claim = score_claim(
            statement="Lithium iron phosphate battery density improved significantly",
            sources=sources,
        )
        assert claim.status != ClaimStatus.VERIFIED, \
            "VERIFIED must be blocked when relevance is low"
        assert any("Relevance gate" in lim for lim in claim.limitations)

    def test_relevance_score_4_forces_unverified(self):
        """Score <= 4 must force UNVERIFIED regardless of other criteria."""
        sources = [
            EvidenceItem(
                source_title="NREL",
                url_or_id="https://nrel.gov/solar",
                source_type="web",
                authority_level="high",
                passage="The sun is yellow.",
                publication_date="2025-01-01",
            ),
        ]
        claim = score_claim(
            statement="Lithium iron phosphate battery density improved significantly",
            sources=sources,
        )
        assert claim.status == ClaimStatus.UNVERIFIED

    def test_high_relevance_allows_verified(self):
        sources = [
            EvidenceItem(
                source_title="NREL",
                url_or_id="https://nrel.gov/battery",
                source_type="web",
                authority_level="high",
                passage="Lithium iron phosphate battery density improved significantly in recent testing cycles.",
                publication_date="2025-01-01",
            ),
            EvidenceItem(
                source_title="Reuters",
                url_or_id="https://reuters.com/battery",
                source_type="web",
                authority_level="high",
                passage="Battery density for lithium iron phosphate cells showed significant improvement.",
                publication_date="2025-03-01",
            ),
        ]
        claim = score_claim(
            statement="Lithium iron phosphate battery density improved significantly",
            sources=sources,
        )
        assert claim.status == ClaimStatus.VERIFIED


# ---------------------------------------------------------------------------
# F-4  Recency bug
# ---------------------------------------------------------------------------

class TestRecency:
    def test_outdated_branch_is_reachable(self):
        """Source 5-10 years old yields 5 pts (the previously unreachable branch)."""
        cur = datetime.datetime.now().year
        score = _per_source_recency("2018-01-01", cur)
        assert score == 5

    def test_very_old_branch_is_reachable(self):
        """Source > 10 years old yields 2 pts."""
        cur = datetime.datetime.now().year
        score = _per_source_recency("2010-01-01", cur)
        assert score == 2

    def test_moderately_dated_yields_10(self):
        cur = datetime.datetime.now().year
        score = _per_source_recency(f"{cur - 3}-06-01", cur)
        assert score == 10

    def test_recent_source_yields_15(self):
        cur = datetime.datetime.now().year
        score = _per_source_recency(f"{cur - 1}-06-01", cur)
        assert score == 15

    def test_one_recent_source_cannot_grant_full_credit_alone(self):
        """
        Old high-authority primary + new low-authority bystander.
        Weighted average ensures old high-authority source is not obscured.
        """
        cur = datetime.datetime.now().year
        old_high = EvidenceItem(
            source_title="Old Study",
            url_or_id="https://nrel.gov/old",
            source_type="web",
            authority_level="high",
            passage="Fact.",
            publication_date="2010-01-01",
        )
        new_low = EvidenceItem(
            source_title="New Blog",
            url_or_id="https://randomblog.xyz/post",
            source_type="web",
            authority_level="low",
            passage="Fact.",
            publication_date=f"{cur}-01-01",
        )
        score, _ = assess_recency([old_high, new_low])
        assert score <= 8, (
            f"One recent low-authority source must not hide old high-authority source; got {score}"
        )


# ---------------------------------------------------------------------------
# F-5  Critical claims
# ---------------------------------------------------------------------------

class TestCriticalClaims:
    def test_disputed_critical_claim_caps_aggregate_at_59(self):
        """
        Several verified minor claims cannot hide a key disputed claim.
        """
        good_sources = lambda i: [
            EvidenceItem(
                source_title="NREL",
                url_or_id=f"https://nrel.gov/region{i}",
                source_type="web",
                authority_level="high",
                passage=f"Solar capacity grew significantly in region {i} during the year.",
                publication_date="2025-01-01",
            ),
            EvidenceItem(
                source_title="Reuters",
                url_or_id=f"https://reuters.com/region{i}",
                source_type="web",
                authority_level="high",
                passage=f"Solar capacity significantly expanded in region {i}.",
                publication_date="2025-01-01",
            ),
        ]
        verified_claims = [
            score_claim(
                f"Solar capacity grew significantly in region {i}",
                sources=good_sources(i),
            )
            for i in range(4)
        ]
        critical_disputed = score_claim(
            "Solar capacity grew significantly this year",
            sources=good_sources(99),
            has_conflicts=True,
            conflict_resolved=False,
            is_critical=True,
        )
        assert critical_disputed.status == ClaimStatus.DISPUTED

        agg = compute_aggregate_evidence_strength(verified_claims + [critical_disputed])
        assert agg.overall_score <= 59, (
            f"Critical disputed claim must cap aggregate at 59, got {agg.overall_score}"
        )
        assert any("59" in d or "critical" in d.lower() for d in agg.deductions)

    def test_explicit_is_critical_flag_caps_at_59(self):
        """A claim with is_critical=True that is unverified also triggers the 59 cap."""
        claim1 = score_claim(
            "Core company valuation is precisely $10B",
            sources=[_ev("https://randomblog.xyz", authority="low", passage="Maybe valued high")],
            is_critical=True,
        )
        assert claim1.status == ClaimStatus.UNVERIFIED
        agg = compute_aggregate_evidence_strength([claim1])
        assert agg.overall_score <= 59

    def test_non_critical_disputed_does_not_hard_cap(self):
        good_sources = lambda i: [
            EvidenceItem(
                source_title="NREL",
                url_or_id=f"https://nrel.gov/region{i}",
                source_type="web",
                authority_level="high",
                passage=f"Solar capacity grew significantly in region {i}.",
                publication_date="2025-01-01",
            ),
            EvidenceItem(
                source_title="Reuters",
                url_or_id=f"https://reuters.com/region{i}",
                source_type="web",
                authority_level="high",
                passage=f"Solar capacity significantly expanded in region {i}.",
                publication_date="2025-01-01",
            ),
        ]
        verified_claims = [
            score_claim(f"Solar capacity grew significantly in region {i}", sources=good_sources(i))
            for i in range(5)
        ]
        agg = compute_aggregate_evidence_strength(verified_claims)
        assert agg.overall_score > 59


# ---------------------------------------------------------------------------
# F-6  No double penalty
# ---------------------------------------------------------------------------

class TestNoDoublePenalty:
    def test_unverified_claim_not_penalised_twice(self):
        verified_claim = score_claim(
            "Utility-scale solar installations increased 30 percent in 2024",
            sources=[
                EvidenceItem(
                    source_title="NREL",
                    url_or_id="https://nrel.gov/solar",
                    source_type="web",
                    authority_level="high",
                    passage="Utility-scale solar installations increased 30 percent in 2024.",
                    publication_date="2025-01-01",
                ),
                EvidenceItem(
                    source_title="Reuters",
                    url_or_id="https://reuters.com/solar",
                    source_type="web",
                    authority_level="high",
                    passage="Solar installations increased 30 percent according to federal data.",
                    publication_date="2025-01-01",
                ),
            ],
        )
        unverified_claim = score_claim(
            "Quantum battery storage is commercially available",
            sources=[_ev("https://randomblog.xyz", authority="low",
                         passage="Quantum batteries might be cool someday.")],
        )

        agg = compute_aggregate_evidence_strength([verified_claim, unverified_claim])

        for d in agg.deductions:
            if "unverified" in d.lower() or "lack sufficient" in d.lower():
                assert "no additional deduction" in d.lower() or "already reflected" in d.lower(), \
                    f"Old double-penalty language found in deductions: {d!r}"

        assert agg.overall_score >= unverified_claim.rubric_score - 5


# ---------------------------------------------------------------------------
# F-7  Deductions: Per-claim & per-criterion points lost (Item 7)
# ---------------------------------------------------------------------------

class TestDeductionsAndPointsLost:
    def test_claim_record_has_points_lost_and_criterion_breakdown(self):
        """ClaimRecord must contain points_lost and criterion_points_lost."""
        source = EvidenceItem(
            source_title="Industry Blog",
            url_or_id="https://techcrunch.com/article",
            source_type="web",
            authority_level="medium",
            passage="Electric vehicles increased slightly in 2024.",
            publication_date="2021-01-01",  # 5 years old
        )
        claim = score_claim("Electric vehicles increased slightly in 2024", sources=[source])
        
        assert hasattr(claim, "points_lost")
        assert hasattr(claim, "criterion_points_lost")
        assert claim.points_lost == 100 - claim.rubric_score
        assert claim.points_lost > 0
        
        # Verify all 5 criteria are present in criterion_points_lost
        for crit in CRITERION_MAX_POINTS:
            assert crit in claim.criterion_points_lost
            assert claim.criterion_points_lost[crit] == CRITERION_MAX_POINTS[crit] - claim.rubric_breakdown[crit]

    def test_deduction_items_have_structured_data(self):
        """deduction_items must contain criterion, points_lost, max_points, and reason."""
        source = EvidenceItem(
            source_title="Blog",
            url_or_id="https://randomblog.xyz/post",
            source_type="web",
            authority_level="low",
            passage="Irrelevant passage.",
        )
        claim = score_claim("Completely different topic statement", sources=[source])
        
        assert hasattr(claim, "deduction_items")
        assert len(claim.deduction_items) > 0
        for item in claim.deduction_items:
            assert item.criterion in CRITERION_MAX_POINTS
            assert item.points_lost > 0
            assert item.max_points == CRITERION_MAX_POINTS[item.criterion]
            assert len(item.reason) > 0

    def test_aggregate_evidence_strength_points_lost_by_criterion(self):
        """EvidenceStrengthScore must include points_lost_by_criterion and claim_deductions."""
        claim1 = score_claim(
            "Claim 1 statement",
            sources=[_ev("https://nrel.gov/test", passage="Claim 1 statement", authority="high")]
        )
        claim2 = score_claim(
            "Claim 2 statement",
            sources=[_ev("https://randomblog.xyz", passage="Unrelated", authority="low")]
        )
        agg = compute_aggregate_evidence_strength([claim1, claim2])
        
        assert hasattr(agg, "points_lost_by_criterion")
        assert len(agg.points_lost_by_criterion) == 5
        for crit, max_pts in CRITERION_MAX_POINTS.items():
            assert crit in agg.points_lost_by_criterion
            assert agg.points_lost_by_criterion[crit] >= 0.0

        assert hasattr(agg, "claim_deductions")
        assert len(agg.claim_deductions) == 2
        assert agg.claim_deductions[0].claim_id == claim1.claim_id
        assert agg.claim_deductions[1].claim_id == claim2.claim_id

    def test_deductions_linked_to_claim_id_and_criterion(self):
        """Deductions list in aggregate must link to claim_id and criterion."""
        claim = score_claim(
            "Claim requiring inference",
            sources=[_ev("https://randomblog.xyz/test", passage="Vague hints", authority="low")]
        )
        agg = compute_aggregate_evidence_strength([claim])
        
        # At least one deduction should reference claim.claim_id
        matching_deductions = [d for d in agg.deductions if claim.claim_id in d]
        assert len(matching_deductions) > 0, "Deductions must link to claim_id"
        # Check that a criterion name is present
        assert any("Source Authority" in d or "Direct Relevance" in d for d in matching_deductions)


# ---------------------------------------------------------------------------
# Original passing tests (kept for regression)
# ---------------------------------------------------------------------------

class TestOriginalTests:
    def test_source_authority_gov(self):
        gov_source = [EvidenceItem(
            source_title="NREL Report",
            url_or_id="https://www.nrel.gov/research/pv.html",
            source_type="web",
            passage="Solar efficiency reached 24 percent.",
            authority_level="high",
        )]
        score, notes = assess_source_authority(gov_source)
        assert score == 30
        assert any("High-authority" in n for n in notes)

    def test_source_authority_blog(self):
        blog_source = [EvidenceItem(
            source_title="Random Blog",
            url_or_id="https://myenergyblog.xyz/post",
            source_type="web",
            passage="Solar panels are cool.",
            authority_level="low",
        )]
        score, notes = assess_source_authority(blog_source)
        assert score <= 15

    def test_corroboration_multi(self):
        sources_multi = [
            EvidenceItem(source_title="S1", url_or_id="https://nature.com/articles/1",
                         passage="Fact", authority_level="high"),
            EvidenceItem(source_title="S2", url_or_id="https://reuters.com/energy/1",
                         passage="Fact", authority_level="high"),
            EvidenceItem(source_title="S3", url_or_id="https://bloomberg.com/news/1",
                         passage="Fact", authority_level="high"),
        ]
        score, _ = assess_independent_corroboration(sources_multi)
        assert score == 25

    def test_corroboration_single(self):
        single = [EvidenceItem(source_title="S1", url_or_id="https://nature.com/articles/1",
                               passage="Fact", authority_level="high")]
        score, _ = assess_independent_corroboration(single)
        assert score == 14

    def test_direct_relevance_high(self):
        sources = [EvidenceItem(
            source_title="Energy Storage",
            url_or_id="https://nrel.gov/battery",
            passage="Lithium iron phosphate battery density improved significantly in recent testing cycles.",
            authority_level="high",
        )]
        score, _ = assess_direct_relevance(
            "Lithium iron phosphate battery density improved significantly", sources
        )
        assert score == 20

    def test_direct_relevance_low(self):
        sources = [EvidenceItem(
            source_title="Energy Storage",
            url_or_id="https://nrel.gov/battery",
            passage="Lithium iron phosphate battery density improved significantly in recent testing cycles.",
            authority_level="high",
        )]
        score_low, _ = assess_direct_relevance("Hydroelectric turbine operations in Norway", sources)
        assert score_low < 10

    def test_score_claim_and_aggregate(self):
        sources = [
            EvidenceItem(
                source_title="NREL Clean Energy Report",
                url_or_id="https://www.nrel.gov/solar.html",
                publication_date="2025-05-10",
                passage="Utility-scale solar installations increased 30% year-over-year in 2024.",
                authority_level="high",
            ),
            EvidenceItem(
                source_title="Reuters Energy News",
                url_or_id="https://www.reuters.com/business/energy/solar-growth-2024",
                publication_date="2025-06-01",
                passage="Utility-scale solar capacity grew 30 percent according to federal metrics.",
                authority_level="high",
            ),
        ]
        claim = score_claim(
            statement="Utility-scale solar installations increased 30% in 2024",
            sources=sources,
            has_conflicts=False,
            conflict_resolved=True,
        )
        assert claim.rubric_score >= 80
        assert claim.status == ClaimStatus.VERIFIED
        assert claim.relationship == ClaimRelationship.SUPPORTS

        aggregate = compute_aggregate_evidence_strength([claim])
        assert aggregate.overall_score >= 80
        assert aggregate.label == "heuristic"
        assert aggregate.verified_claims_count == 1
        assert "heuristic" in aggregate.explanation
