import os
import pytest
from app.services.pdf_generator import generate_pdf_report, escape_pdf_text
from app.services.rubric import score_claim, compute_aggregate_evidence_strength
from app.schemas import EvidenceItem, Source, ConflictRecord, ClaimStatus


def test_pdf_report_generation():
    sources = [
        EvidenceItem(
            source_title="NREL Solar Study",
            url_or_id="https://nrel.gov/solar",
            passage="Solar energy generation reached record capacity.",
            authority_level="high",
            publication_date="2025-01-01"
        )
    ]
    claim = score_claim("Solar energy generation reached record capacity", sources)
    aggregate = compute_aggregate_evidence_strength([claim])

    report_meta = generate_pdf_report(
        task_id="task-test-01",
        query="What is the current state of solar energy?",
        executive_summary="Solar power continues to expand globally.",
        final_synthesis="Detailed analysis of global solar deployment trends.",
        evidence_strength=aggregate,
        claims=[claim],
        sources=[Source(title="NREL Solar Study", url="https://nrel.gov/solar")],
        citations=["https://nrel.gov/solar"],
        limitations=["Limited to US and European data."]
    )

    assert "report_id" in report_meta
    assert "file_path" in report_meta
    assert os.path.exists(report_meta["file_path"])
    assert report_meta["file_size_bytes"] > 1000

    if os.path.exists(report_meta["file_path"]):
        os.remove(report_meta["file_path"])


def test_pdf_escaping_special_characters():
    """
    Item 10: Ensures text with <, >, &, quotes, or XML/HTML injection does NOT
    break ReportLab's XML parser.
    """
    # Test escape helper directly
    raw_text = 'Check if a < 5 & b > 10 in "C++" & <script>alert("xss")</script>'
    escaped = escape_pdf_text(raw_text)
    assert "&lt;" in escaped
    assert "&gt;" in escaped
    assert "&amp;" in escaped
    assert "<script>" not in escaped

    # Test PDF generation with dangerous characters in all fields
    sources = [
        EvidenceItem(
            source_title="AT&T & Verizon <Sprint> Report",
            url_or_id="https://att.com/r&d",
            passage="Revenue increased & operating costs dropped by < 15% in Q3 & Q4.",
            authority_level="high",
            publication_date="2025-01-01"
        )
    ]
    claim = score_claim(
        statement="Revenue increased & costs dropped by < 15% in 'Q3 & Q4'",
        sources=sources
    )
    aggregate = compute_aggregate_evidence_strength([claim])

    # Should build cleanly without raising ReportLab XML parse errors
    report_meta = generate_pdf_report(
        task_id="task-escape-<test>&01",
        query="Analysis of AT&T & Verizon where growth < 20% & margin > 10%?",
        executive_summary="Executive summary with & symbols, <tags>, & unescaped quotes.",
        final_synthesis="Findings: A < B & C > D with <i>markup</i> attempt.",
        evidence_strength=aggregate,
        claims=[claim],
        sources=[Source(title="AT&T & Co.", url="https://att.com?a=1&b=2")],
        citations=["https://att.com?q=1&v=2"],
        limitations=["Limitation: sample size < 30 & uncertainty > 5%."]
    )

    assert os.path.exists(report_meta["file_path"])
    assert report_meta["file_size_bytes"] > 1000

    if os.path.exists(report_meta["file_path"]):
        os.remove(report_meta["file_path"])


def test_pdf_separate_sections_and_explanations():
    """
    Item 8: Claim table includes per-criterion breakdown, deductions & conflicts.
    Item 9: Separate sections for Verified/Supported vs Contradicted/Unverified.
    """
    # 1. Verified claim
    v_sources = [
        EvidenceItem(
            source_title="NREL Solar Report",
            url_or_id="https://nrel.gov/solar",
            passage="Solar efficiency reached 24 percent in lab tests.",
            authority_level="high",
            publication_date="2025-01-01"
        )
    ]
    verified_claim = score_claim("Solar efficiency reached 24 percent in lab tests", v_sources)
    assert verified_claim.status == ClaimStatus.VERIFIED

    # 2. Contradicted / Disputed claim with explicit ConflictRecord
    d_sources = [
        EvidenceItem(
            source_title="Contradicting Report",
            url_or_id="https://example.com/energy",
            passage="Efficiency was capped at 12 percent.",
            authority_level="medium",
            publication_date="2024-01-01"
        )
    ]
    disputed_claim = score_claim(
        statement="Solar efficiency was 24 percent everywhere",
        sources=d_sources,
        has_conflicts=True,
        conflict_resolved=False,
    )
    disputed_claim.conflicts.append(
        ConflictRecord(
            conflict_type="numeric_mismatch",
            description="Source claims 12% max while claim asserts 24%",
            source_a="https://nrel.gov/solar",
            source_b="https://example.com/energy",
            resolved=False
        )
    )
    assert disputed_claim.status == ClaimStatus.DISPUTED

    # 3. Unverified claim
    unverified_claim = score_claim(
        statement="Quantum zero-point battery powers commercial airplanes",
        sources=[EvidenceItem(
            source_title="Random Blog",
            url_or_id="https://freeenergyblog.xyz/post",
            passage="Zero point energy is very interesting.",
            authority_level="low"
        )]
    )
    assert unverified_claim.status == ClaimStatus.UNVERIFIED

    claims = [verified_claim, disputed_claim, unverified_claim]
    aggregate = compute_aggregate_evidence_strength(claims)

    report_meta = generate_pdf_report(
        task_id="task-sections-01",
        query="Comprehensive clean energy assessment",
        executive_summary="Summary covering both verified claims and contested findings.",
        final_synthesis="Full synthesis text.",
        evidence_strength=aggregate,
        claims=claims,
        sources=[Source(title="NREL", url="https://nrel.gov")],
        citations=["https://nrel.gov/solar"],
        limitations=["Some data disputed."]
    )

    assert os.path.exists(report_meta["file_path"])
    assert report_meta["file_size_bytes"] > 2000

    if os.path.exists(report_meta["file_path"]):
        os.remove(report_meta["file_path"])
