import os
import pytest
from app.services.pdf_generator import generate_pdf_report
from app.services.rubric import score_claim, compute_aggregate_evidence_strength
from app.schemas import EvidenceItem, Source

def test_pdf_report_generation():
    sources = [
        EvidenceItem(
            source_title="NREL Solar Study",
            url_or_id="https://nrel.gov/solar",
            passage="Solar energy generation reached record capacity.",
            authority_level="high"
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

    # Clean up test artifact if desired
    if os.path.exists(report_meta["file_path"]):
        os.remove(report_meta["file_path"])
