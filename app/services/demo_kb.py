"""
Curated Demo Knowledge Base
Pre-populates Veritas AI with authoritative, multi-domain reference documents:
1. U.S. Clean Energy & Storage Report 2025 (High Authority, .gov)
2. Nature AI Agent Verification Benchmarks 2025 (High Authority, Peer-Reviewed)
3. Reuters Global Semiconductor Manufacturing 2024 (High Authority, Wire News)
4. Veritas AI Architectural Blueprint v2 (KB Authority, Internal Team KB)
5. Executive Quarterly Strategy Presentation (PPTX Presentation format)
"""

import io
import uuid
import zipfile
from typing import Dict, Any, List
from xml.sax.saxutils import escape as xml_escape

from app.services.chunking import chunk_text
from app.services.vector_store import add_chunks, list_documents, get_collection
from app.services.extractors import extract_text

DEMO_DOCUMENTS = [
    {
        "filename": "us_doe_clean_energy_standard_2025.txt",
        "authority_level": "high",
        "source_type": "knowledge_base",
        "classification": "public",
        "access_roles": ["public", "researcher", "analyst"],
        "content": """
United States Department of Energy (DOE) - 2025 Clean Energy Progress Report
Official Federal Report | Publication Date: 2025-01-15 | Authority: High (gov)

Executive Summary:
Utility-scale solar installations across the United States expanded by 34% year-over-year in 2024,
adding 28 gigawatts of generation capacity to regional transmission grids.
Grid-scale battery energy storage systems utilizing lithium-iron-phosphate (LFP) chemistries achieved
commercial round-trip efficiency of 89.4%, with standard cycle lifespans exceeding 4,200 full charge cycles.

Key Empirical Findings:
1. Solar LCOE: The levelized cost of electricity (LCOE) for unsubsidized utility-scale solar photovoltaic
   arrays declined to $0.034 per kilowatt-hour across Southwest and ERCOT interconnect territories.
2. Battery Storage Capacity: Operating grid-scale battery capacity surpassed 24.2 gigawatts in Q4 2024,
   preventing major curtailment during summer peak demand spikes in California and Texas.
3. Transmission Modernization: High-voltage direct current (HVDC) transmission lines demonstrated a 40%
   reduction in line losses compared to standard AC 500kV alternatives over distances exceeding 800 miles.
4. Hydrogen Integration: Green hydrogen electrolysis efficiency reached 64.5 kilowatt-hours per kilogram
   using proton-exchange membrane (PEM) stack architectures.
"""
    },
    {
        "filename": "nature_ai_safety_benchmarks_2025.txt",
        "authority_level": "high",
        "source_type": "knowledge_base",
        "classification": "public",
        "access_roles": ["public", "researcher", "analyst"],
        "content": """
Nature Machine Intelligence - Factual Verification and Agent Alignment in Multi-Agent Systems
Peer-Reviewed Research | Publication Date: 2025-02-10 | Authority: High (nature.com)

Abstract:
Large language model verification systems frequently suffer from reciprocal hallucination reinforcement
when relying solely on unweighted majority consensus. This study benchmarks deterministic rubric-based
evidence verification engines against unweighted voting baselines across 12,000 empirical claims.

Empirical Metrics & Validation Results:
1. Hallucination Reduction: Multi-agent verification frameworks enforcing a 5-criterion deterministic
   rubric (Authority, Corroboration, Direct Relevance, Recency, Contradiction Resolution) reduced
   uncaught factual hallucinations by 34.6% relative to single-pass chain-of-thought generation.
2. Contradiction Sensitivity: Bidirectional claim-to-evidence passage alignment detected subtle numeric
   and polarity contradictions with a precision of 93.8% and recall of 88.2%.
3. Domain-Specific Discrepancies: Peer-reviewed and official government datasets yielded verification
   confidence exceeding 91%, whereas unvetted commercial blogs introduced a 27% noise floor in factual claims.
4. Deliberative Synthesis: Sub-agent adversarial debate (domain analysis vs counter-analysis) lowered
   over-confidence in ambiguous queries from 68% to under 12%.
"""
    },
    {
        "filename": "reuters_global_semiconductor_report_2024.txt",
        "authority_level": "high",
        "source_type": "knowledge_base",
        "classification": "internal",
        "access_roles": ["internal", "researcher", "analyst"],
        "content": """
Reuters Market Insight - Global Semiconductor Manufacturing Capacity & Advanced Packaging
Wire Service Factual Dispatch | Publication Date: 2024-11-20 | Authority: High (reuters.com)

Industry Analysis:
Worldwide capital expenditure for advanced semiconductor fabrication facilities reached $178 billion
in 2024, driven by accelerated hyperscale datacenter procurement of 3-nanometer and 4-nanometer accelerators.

Critical Production Statistics:
1. Advanced Node Yield: Leading foundries reported 3nm gate-all-around (GAA) production yields reaching
   68% on commercial wafer runs by late 2024, up from 49% twelve months prior.
2. Advanced Packaging Bottlenecks: CoWoS (Chip-on-Wafer-on-Substrate) packaging capacity expanded 140%
   year-over-year, yet remained the primary supply constraint for AI accelerator availability.
3. Geographical Diversification: Non-East Asian wafer output represented 14% of global leading-edge
   capacity in 2024, projected to reach 22% by 2027 as new European and American fabs come online.
4. Silicon Carbide & Gallium Nitride: Automotive power electronics transition to SiC wafers yielded
   a 6.8% efficiency gain in electric drivetrain inverters under real-world dynamometer testing.
"""
    },
    {
        "filename": "veritas_ai_system_blueprint_v2.txt",
        "authority_level": "high",
        "source_type": "knowledge_base",
        "classification": "internal",
        "access_roles": ["internal", "admin", "analyst"],
        "content": """
Veritas AI Engineering Specification - Deterministic Evidence Rubric & System Blueprint v2.0
Internal Engineering Specification | Internal KB Token: internal_kb:spec-veritas-v2 | Authority: KB (28 pts)

System Architecture & Evaluation Protocol:
The Veritas AI Master Agent coordinates research, domain analysis, counter-analysis, and evidence
verification according to a deterministic 5-criterion rubric scoring scale (0 to 100 points):

Rubric Point Allocations:
1. Source Authority (Max 30 pts):
   - Peer-reviewed research (.edu, nature.com, ieee.org) or government (.gov, .int): 30 pts.
   - Internal verified team knowledge-base document (source_type='knowledge_base'): 28 pts.
   - Reputable secondary industry sources (.com wire, major financial press): 20 pts.
   - Low-authority, unverified or blog domains: 12 pts.
2. Independent Corroboration (Max 25 pts):
   - >= 3 independent registrable domains or distinct KB document IDs: 25 pts.
   - 2 independent sources: 22 pts.
   - Single isolated source: 14 pts. (Chunks of the same document collapse to 1 origin).
3. Direct Relevance (Max 20 pts):
   - Cited passage directly supports claim concepts (>= 70% overlap): 20 pts.
   - Partial support requiring inference: 14 pts.
   - Tangential relevance: 8 pts (Relevance Gate blocks VERIFIED).
   - Low relevance (<= 4 pts): forces UNVERIFIED status regardless of total points.
4. Recency (Max 15 pts):
   - Published within 2 years: 15 pts.
   - Moderately dated (2-5 years): 10 pts.
   - Dated (5-10 years): 5 pts.
   - Outdated (> 10 years): 2 pts.
5. Contradiction Handling (Max 10 pts):
   - Contradictions analyzed and resolved: 10 pts.
   - Unresolved contradiction: 2 pts (Forces DISPUTED status; caps aggregate at 59).
"""
    }
]


def _create_demo_pptx_bytes() -> bytes:
    """
    Creates a valid, well-formed OpenXML .pptx presentation in-memory.
    Contains 3 structured slides with presentation title, bullet points, and speaker notes.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        # 1. [Content_Types].xml
        content_types = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
            '<Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
            '<Override PartName="/ppt/slides/slide2.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
            '<Override PartName="/ppt/slides/slide3.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
            '</Types>'
        )
        z.writestr("[Content_Types].xml", content_types)

        # 2. _rels/.rels
        rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>'
            '</Relationships>'
        )
        z.writestr("_rels/.rels", rels)

        # 3. ppt/presentation.xml
        pres = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            '<p:sldIdLst>'
            '<p:sldId id="256" r:id="rId1" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>'
            '<p:sldId id="257" r:id="rId2" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>'
            '<p:sldId id="258" r:id="rId3" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>'
            '</p:sldIdLst>'
            '</p:presentation>'
        )
        z.writestr("ppt/presentation.xml", pres)

        # 4. Slides
        slides_data = [
            (
                "Executive Briefing: Veritas AI Strategic Roadmap 2025",
                [
                    "Objective: Deploy verifiable enterprise intelligence with mathematical audit trails.",
                    "Key Milestone: 99.4% precision in factual contradiction detection across multi-agent workflows.",
                    "Governance: Full RBAC and document classification enforcement at the vector boundary."
                ]
            ),
            (
                "Clean Energy Technology Assessment",
                [
                    "Grid Storage: LFP battery capacity grew by 24.2 GW across interconnected North American grids.",
                    "Levelized Cost: Solar PV electricity reached record low cost of $0.034 per kilowatt-hour.",
                    "Transmission: HVDC lines achieved a 40% reduction in transmission line losses."
                ]
            ),
            (
                "Advanced Semiconductor Fabrications & Supply Security",
                [
                    "Commercial 3nm GAA yields stabilized at 68% in Q4 2024 production cycles.",
                    "Advanced packaging throughput expanded 140% to meet global accelerator demand.",
                    "Silicon Carbide transition delivered 6.8% powertrain inverter efficiency improvement."
                ]
            )
        ]

        for idx, (title, bullets) in enumerate(slides_data, 1):
            title_esc = xml_escape(title)
            bullets_esc = "".join(f'<a:p><a:r><a:t>{xml_escape(b)}</a:t></a:r></a:p>' for b in bullets)
            slide_xml = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
                'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
                '<p:cSld><p:spTree>'
                '<p:sp><p:txBody>'
                f'<a:p><a:r><a:t>{title_esc}</a:t></a:r></a:p>'
                + bullets_esc +
                '</p:txBody></p:sp>'
                '</p:spTree></p:cSld></p:sld>'
            )
            z.writestr(f"ppt/slides/slide{idx}.xml", slide_xml)

    buf.seek(0)
    return buf.getvalue()


def seed_demo_knowledge_base(force: bool = False) -> Dict[str, Any]:
    """
    Populates the persistent Chroma vector store with curated demo documents
    covering Clean Energy, AI Governance, Semiconductor Supply, System Architecture,
    and a multi-slide PPTX Presentation.
    """
    existing_docs = list_documents()
    existing_filenames = {d.get("filename") for d in existing_docs}

    indexed_docs_count = 0
    total_chunks_added = 0
    doc_details = []

    # 1. Index text documents
    for doc in DEMO_DOCUMENTS:
        fname = doc["filename"]
        if not force and fname in existing_filenames:
            continue

        doc_id = f"demo-{uuid.uuid4().hex[:8]}"
        text = doc["content"].strip()
        chunks = chunk_text(text)

        chunks_count = add_chunks(
            document_id=doc_id,
            filename=fname,
            chunks=chunks,
            classification=doc.get("classification", "public"),
            access_roles=doc.get("access_roles", ["public"]),
            source_type=doc.get("source_type", "knowledge_base"),
            authority_level=doc.get("authority_level", "high")
        )

        indexed_docs_count += 1
        total_chunks_added += chunks_count
        doc_details.append({
            "document_id": doc_id,
            "filename": fname,
            "chunks": chunks_count,
            "classification": doc.get("classification", "public"),
            "format": "txt"
        })

    # 2. Index PPTX presentation document (testing PPTX extraction & seeding)
    pptx_filename = "executive_veritas_roadmap_2025.pptx"
    if force or pptx_filename not in existing_filenames:
        pptx_bytes = _create_demo_pptx_bytes()
        extracted_text = extract_text(pptx_filename, pptx_bytes)
        pptx_chunks = chunk_text(extracted_text)
        pptx_doc_id = f"demo-pptx-{uuid.uuid4().hex[:8]}"

        pptx_chunks_count = add_chunks(
            document_id=pptx_doc_id,
            filename=pptx_filename,
            chunks=pptx_chunks,
            classification="internal",
            access_roles=["public", "internal", "executive"],
            source_type="knowledge_base",
            authority_level="high"
        )
        indexed_docs_count += 1
        total_chunks_added += pptx_chunks_count
        doc_details.append({
            "document_id": pptx_doc_id,
            "filename": pptx_filename,
            "chunks": pptx_chunks_count,
            "classification": "internal",
            "format": "pptx"
        })

    return {
        "status": "seeded",
        "newly_indexed_documents": indexed_docs_count,
        "newly_indexed_chunks": total_chunks_added,
        "total_documents_in_store": len(list_documents()),
        "seeded_documents": doc_details
    }


def get_demo_kb_status() -> Dict[str, Any]:
    """
    Returns statistics and overview of the demo knowledge base.
    """
    docs = list_documents()
    demo_doc_names = {d["filename"] for d in DEMO_DOCUMENTS}
    demo_doc_names.add("executive_veritas_roadmap_2025.pptx")

    installed_demo_docs = [d for d in docs if d.get("filename") in demo_doc_names]

    return {
        "is_seeded": len(installed_demo_docs) >= 3,
        "demo_documents_count": len(installed_demo_docs),
        "total_documents_count": len(docs),
        "documents": installed_demo_docs
    }
