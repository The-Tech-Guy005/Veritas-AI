"""
PDF Report Generator
Builds a professional executive PDF report using ReportLab.
Includes:
- Veritas AI header & task metadata
- Evidence Strength Score Card (with 5-criteria breakdown)
- Claim-Level Verification Records (Verified, Disputed, Partially Supported)
- Executive Summary & Synthesis
- Traceable Sources & Citations
- Disclosed Limitations & Uncertainty Notes
"""

import os
import uuid
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from app.config import settings
from app.schemas import ClaimRecord, EvidenceStrengthScore, Source, ClaimStatus

def generate_pdf_report(
    task_id: str,
    query: str,
    executive_summary: str,
    final_synthesis: str,
    evidence_strength: EvidenceStrengthScore,
    claims: List[ClaimRecord],
    sources: List[Source],
    citations: List[str],
    limitations: List[str]
) -> Dict[str, Any]:
    """
    Generates a PDF report file in settings.reports_dir and returns report metadata.
    """
    report_id = f"report-{uuid.uuid4().hex[:10]}"
    filename = f"{report_id}.pdf"
    file_path = os.path.join(settings.reports_dir, filename)

    # Ensure target directory exists
    Path(settings.reports_dir).mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        file_path,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#0F172A'),
        spaceAfter=6
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#475569'),
        spaceAfter=12
    )
    h2_style = ParagraphStyle(
        'SectionH2',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=colors.HexColor('#1E293B'),
        spaceBefore=12,
        spaceAfter=6
    )
    body_style = ParagraphStyle(
        'BodyDark',
        parent=styles['BodyText'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor('#1E293B')
    )
    score_big_style = ParagraphStyle(
        'ScoreBig',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=26,
        leading=30,
        textColor=colors.HexColor('#2563EB'),
        alignment=1
    )
    badge_style = ParagraphStyle(
        'Badge',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.white,
        alignment=1
    )
    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        textColor=colors.HexColor('#0F172A')
    )

    story = []

    # 1. Header Banner
    story.append(Paragraph("VERITAS AI — EVIDENCE VERIFICATION REPORT", title_style))
    created_date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    story.append(Paragraph(
        f"<b>Task ID:</b> {task_id} &nbsp;|&nbsp; <b>Report ID:</b> {report_id} &nbsp;|&nbsp; <b>Generated:</b> {created_date}",
        subtitle_style
    ))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#3B82F6'), spaceAfter=10))

    # 2. Inquiry & Scope
    story.append(Paragraph("<b>Inquiry & Scope:</b>", h2_style))
    story.append(Paragraph(f"<i>\"{query}\"</i>", body_style))
    story.append(Spacer(1, 8))

    # 3. Evidence Strength Card
    story.append(Paragraph("<b>Evidence-Strength Assessment (Heuristic):</b>", h2_style))
    
    # Rubric Table Data
    breakdown = evidence_strength.rubric_breakdown
    rubric_data = [
        [Paragraph("<b>Rubric Criterion</b>", table_header_style), Paragraph("<b>Max Pts</b>", table_header_style), Paragraph("<b>Assessed Score</b>", table_header_style)],
        [Paragraph("Source Authority", body_style), "30", f"{breakdown.get('source_authority', 0)}"],
        [Paragraph("Independent Corroboration", body_style), "25", f"{breakdown.get('independent_corroboration', 0)}"],
        [Paragraph("Direct Relevance", body_style), "20", f"{breakdown.get('direct_relevance', 0)}"],
        [Paragraph("Recency", body_style), "15", f"{breakdown.get('recency', 0)}"],
        [Paragraph("Contradiction Handling", body_style), "10", f"{breakdown.get('contradiction_handling', 0)}"],
        [Paragraph("<b>Overall Score</b>", table_header_style), Paragraph("<b>100</b>", table_header_style), Paragraph(f"<b>{evidence_strength.overall_score} / 100</b>", table_header_style)]
    ]
    rubric_table = Table(rubric_data, colWidths=[200, 70, 90])
    rubric_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F1F5F9')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#EFF6FF'))
    ]))

    # Score Box
    score_box_data = [
        [Paragraph(f"{evidence_strength.overall_score} / 100", score_big_style)],
        [Paragraph(f"<b>{evidence_strength.label.upper()}</b>", ParagraphStyle('ScoreLabel', fontName='Helvetica-Bold', fontSize=10, textColor=colors.HexColor('#475569'), alignment=1))],
        [Paragraph(f"{evidence_strength.verified_claims_count} Verified &nbsp;|&nbsp; {evidence_strength.partially_supported_count} Partial &nbsp;|&nbsp; {evidence_strength.disputed_claims_count} Disputed", ParagraphStyle('Sub', fontName='Helvetica', fontSize=8, textColor=colors.HexColor('#64748B'), alignment=1))]
    ]
    score_table = Table(score_box_data, colWidths=[160])
    score_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#93C5FD')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6)
    ]))

    assessment_table = Table([[score_table, rubric_table]], colWidths=[170, 370])
    assessment_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(assessment_table)
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"<i>Note: {evidence_strength.explanation}</i>", ParagraphStyle('Note', fontName='Helvetica-Oblique', fontSize=8, textColor=colors.HexColor('#64748B'))))
    story.append(Spacer(1, 10))

    # 4. Executive Summary
    story.append(Paragraph("<b>Executive Summary:</b>", h2_style))
    for p in executive_summary.split("\n"):
        if p.strip():
            story.append(Paragraph(p.strip(), body_style))
            story.append(Spacer(1, 2))
    story.append(Spacer(1, 8))

    # 5. Claim-by-Claim Verification Matrix
    story.append(Paragraph("<b>Claim-by-Claim Verification Matrix:</b>", h2_style))
    claims_table_data = [
        [
            Paragraph("<b>Claim Statement</b>", table_header_style),
            Paragraph("<b>Status</b>", table_header_style),
            Paragraph("<b>Score</b>", table_header_style),
            Paragraph("<b>Source Excerpt / Reference</b>", table_header_style)
        ]
    ]

    for c in claims:
        # Determine status color
        if c.status == ClaimStatus.VERIFIED:
            status_color = colors.HexColor('#16A34A')  # Green
        elif c.status == ClaimStatus.PARTIALLY_SUPPORTED:
            status_color = colors.HexColor('#CA8A04')  # Amber
        elif c.status == ClaimStatus.DISPUTED:
            status_color = colors.HexColor('#DC2626')  # Red
        else:
            status_color = colors.HexColor('#64748B')  # Gray

        status_para = Paragraph(
            f"<font color='{status_color.hexval()}'><b>{c.status.value.upper()}</b></font>",
            body_style
        )
        source_ref = "No sources"
        if c.evidence_sources:
            src = c.evidence_sources[0]
            source_ref = f"<b>{src.source_title[:24]}</b><br/>{src.passage[:110]}..."

        claims_table_data.append([
            Paragraph(c.statement, body_style),
            status_para,
            f"{c.rubric_score}/100",
            Paragraph(source_ref, ParagraphStyle('Passage', fontName='Helvetica', fontSize=7.5, leading=10, textColor=colors.HexColor('#334155')))
        ])

    claims_table = Table(claims_table_data, colWidths=[200, 80, 50, 210])
    claims_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F1F5F9')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4)
    ]))
    story.append(claims_table)
    story.append(Spacer(1, 10))

    # 6. Detailed Synthesis
    story.append(Paragraph("<b>Detailed Findings & Analysis:</b>", h2_style))
    for line in final_synthesis.split("\n"):
        clean_line = line.strip()
        if clean_line.startswith("#"):
            story.append(Paragraph(f"<b>{clean_line.lstrip('#').strip()}</b>", h2_style))
        elif clean_line:
            story.append(Paragraph(clean_line, body_style))
            story.append(Spacer(1, 2))
    story.append(Spacer(1, 8))

    # 7. Traceable Sources & Citations
    story.append(Paragraph("<b>Traceable Sources & Document References:</b>", h2_style))
    if citations:
        for cit in citations:
            story.append(Paragraph(f"• <font color='#2563EB'><u>{cit}</u></font>", body_style))
            story.append(Spacer(1, 2))
    else:
        story.append(Paragraph("• No external web citations or internal document chunks cited.", body_style))
    story.append(Spacer(1, 8))

    # 8. Limitations & Gaps
    story.append(Paragraph("<b>Disclosed Limitations & Uncertainty Gaps:</b>", h2_style))
    if limitations:
        for lim in limitations:
            story.append(Paragraph(f"• {lim}", body_style))
            story.append(Spacer(1, 2))
    else:
        story.append(Paragraph("• No significant evidence gaps reported.", body_style))

    # Build document
    doc.build(story)

    file_size = os.path.getsize(file_path)

    return {
        "report_id": report_id,
        "filename": filename,
        "file_path": file_path,
        "file_size_bytes": file_size,
        "download_url": f"/master/reports/{report_id}/pdf"
    }
