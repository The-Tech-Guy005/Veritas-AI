"""
PDF Report Generator
Builds a professional executive PDF report using ReportLab.
Includes:
- Veritas AI header & task metadata
- Evidence Strength Score Card (with 5-criteria breakdown & points lost)
- Claim-Level Verification Records with per-criterion breakdown, deductions & conflicts
- Dedicated Contradicted / Unverified section
- Full XML/HTML entity escaping to ensure <, >, & in claim text never crash ReportLab
- Executive Summary & Synthesis
- Traceable Sources & Citations
- Disclosed Limitations & Uncertainty Notes
"""

import os
import uuid
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from xml.sax.saxutils import escape as xml_escape

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from app.config import settings
from app.schemas import ClaimRecord, EvidenceStrengthScore, Source, ClaimStatus


def escape_pdf_text(text: Any) -> str:
    """
    Escapes raw text (&, <, >) to ensure ReportLab Paragraph flowables do not
    crash on XML parsing errors.
    """
    if text is None:
        return ""
    return xml_escape(str(text))


def _build_claims_table(
    claims_list: List[ClaimRecord],
    body_style: ParagraphStyle,
    table_header_style: ParagraphStyle,
    is_contradicted_section: bool = False
) -> Table:
    """
    Constructs an evidence matrix table including per-criterion breakdown,
    detailed deductions, and detected conflicts (Item 8).
    """
    header_bg = colors.HexColor('#FFF1F2') if is_contradicted_section else colors.HexColor('#F1F5F9')
    grid_color = colors.HexColor('#FECDD3') if is_contradicted_section else colors.HexColor('#CBD5E1')

    table_data = [
        [
            Paragraph("<b>Claim Statement & Verification Breakdown</b>", table_header_style),
            Paragraph("<b>Status</b>", table_header_style),
            Paragraph("<b>Score</b>", table_header_style),
            Paragraph("<b>Evidence & References</b>", table_header_style)
        ]
    ]

    for c in claims_list:
        # Determine status color
        if c.status == ClaimStatus.VERIFIED:
            status_color = colors.HexColor('#16A34A')  # Green
        elif c.status == ClaimStatus.PARTIALLY_SUPPORTED:
            status_color = colors.HexColor('#CA8A04')  # Amber
        elif c.status == ClaimStatus.DISPUTED:
            status_color = colors.HexColor('#DC2626')  # Red
        else:
            status_color = colors.HexColor('#475569')  # Slate Gray

        status_para = Paragraph(
            f"<font color='{status_color.hexval()}'><b>{escape_pdf_text(c.status.value.upper())}</b></font>",
            body_style
        )

        score_text = f"<b>{c.rubric_score}/100</b>"
        points_lost = getattr(c, "points_lost", 100 - c.rubric_score)
        if points_lost > 0:
            score_text += f"<br/><font size='7' color='#DC2626'>(-{points_lost} pts lost)</font>"

        # 1. Statement & Criteria Breakdown (Item 8 & 10)
        stmt_html = f"<b>{escape_pdf_text(c.statement)}</b><br/>"
        
        bd = c.rubric_breakdown or {}
        stmt_html += (
            f"<font size='7' color='#334155'><b>Criteria Breakdown:</b> "
            f"Auth: {bd.get('source_authority', 0)}/30 | "
            f"Corrob: {bd.get('independent_corroboration', 0)}/25 | "
            f"Relev: {bd.get('direct_relevance', 0)}/20 | "
            f"Recency: {bd.get('recency', 0)}/15 | "
            f"Contrad: {bd.get('contradiction_handling', 0)}/10</font>"
        )

        # 2. Deductions
        c_deductions = getattr(c, "deduction_items", [])
        if c_deductions:
            active_deds = [
                f"{escape_pdf_text(d.criterion.replace('_', ' ').title())}: -{d.points_lost} pts ({escape_pdf_text(d.reason)})"
                for d in c_deductions if d.points_lost > 0
            ]
            if active_deds:
                stmt_html += f"<br/><font size='7' color='#B45309'><b>Deductions:</b> {'; '.join(active_deds[:2])}</font>"
        elif getattr(c, "limitations", []):
            lims = [escape_pdf_text(lim) for lim in c.limitations[:2]]
            stmt_html += f"<br/><font size='7' color='#B45309'><b>Deductions:</b> {'; '.join(lims)}</font>"

        # 3. Conflicts (Item 8)
        conflicts = getattr(c, "conflicts", [])
        if conflicts:
            conf_lines = []
            for cf in conflicts:
                res_str = "Resolved" if cf.resolved else "Unresolved"
                conf_lines.append(f"[{escape_pdf_text(cf.conflict_type)}] {escape_pdf_text(cf.description)} ({res_str})")
            stmt_html += f"<br/><font size='7' color='#DC2626'><b>Conflicts ({len(conflicts)}):</b> {'; '.join(conf_lines)}</font>"
        elif c.status == ClaimStatus.DISPUTED:
            stmt_html += "<br/><font size='7' color='#DC2626'><b>Conflicts:</b> Unresolved contradiction identified between sources.</font>"

        # Source excerpt cell (Item 10)
        source_ref = "No sources cited"
        if c.evidence_sources:
            src = c.evidence_sources[0]
            title_esc = escape_pdf_text(src.source_title[:28])
            pass_esc = escape_pdf_text(src.passage[:110])
            source_ref = f"<b>{title_esc}</b><br/>{pass_esc}..."
            if len(c.evidence_sources) > 1:
                source_ref += f"<br/><font size='7' color='#64748B'>+{len(c.evidence_sources)-1} additional source(s)</font>"

        table_data.append([
            Paragraph(stmt_html, ParagraphStyle('ClaimCell', fontName='Helvetica', fontSize=8, leading=10.5, textColor=colors.HexColor('#0F172A'))),
            status_para,
            Paragraph(score_text, ParagraphStyle('ScoreCell', fontName='Helvetica', fontSize=8, leading=10, textColor=colors.HexColor('#0F172A'), alignment=1)),
            Paragraph(source_ref, ParagraphStyle('Passage', fontName='Helvetica', fontSize=7.5, leading=9.5, textColor=colors.HexColor('#334155')))
        ])

    table = Table(table_data, colWidths=[240, 65, 55, 180])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), header_bg),
        ('GRID', (0, 0), (-1, -1), 0.5, grid_color),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4)
    ]))
    return table


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
        fontSize=12,
        leading=15,
        textColor=colors.HexColor('#1E293B'),
        spaceBefore=10,
        spaceAfter=5
    )
    body_style = ParagraphStyle(
        'BodyDark',
        parent=styles['BodyText'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#1E293B')
    )
    score_big_style = ParagraphStyle(
        'ScoreBig',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=28,
        textColor=colors.HexColor('#2563EB'),
        alignment=1
    )
    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=10.5,
        textColor=colors.HexColor('#0F172A')
    )

    story = []

    # 1. Header Banner
    story.append(Paragraph("VERITAS AI — EVIDENCE VERIFICATION REPORT", title_style))
    created_date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    story.append(Paragraph(
        f"<b>Task ID:</b> {escape_pdf_text(task_id)} &nbsp;|&nbsp; <b>Report ID:</b> {escape_pdf_text(report_id)} &nbsp;|&nbsp; <b>Generated:</b> {created_date}",
        subtitle_style
    ))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#3B82F6'), spaceAfter=10))

    # 2. Inquiry & Scope (Item 10: properly escaped)
    story.append(Paragraph("<b>1. Inquiry & Scope:</b>", h2_style))
    story.append(Paragraph(f"<i>\"{escape_pdf_text(query)}\"</i>", body_style))
    story.append(Spacer(1, 6))

    # 3. Evidence Strength Card with Points Lost (Item 7 & Item 8)
    story.append(Paragraph("<b>2. Evidence-Strength Assessment (Heuristic):</b>", h2_style))
    
    breakdown = evidence_strength.rubric_breakdown or {}
    points_lost_by_crit = getattr(evidence_strength, "points_lost_by_criterion", {})
    rubric_data = [
        [
            Paragraph("<b>Rubric Criterion</b>", table_header_style),
            Paragraph("<b>Max Pts</b>", table_header_style),
            Paragraph("<b>Assessed</b>", table_header_style),
            Paragraph("<b>Points Lost</b>", table_header_style),
        ],
        [
            Paragraph("Source Authority", body_style),
            "30",
            f"{breakdown.get('source_authority', 0)}",
            f"-{points_lost_by_crit.get('source_authority', round(max(0.0, 30.0 - breakdown.get('source_authority', 0)), 1))}"
        ],
        [
            Paragraph("Independent Corroboration", body_style),
            "25",
            f"{breakdown.get('independent_corroboration', 0)}",
            f"-{points_lost_by_crit.get('independent_corroboration', round(max(0.0, 25.0 - breakdown.get('independent_corroboration', 0)), 1))}"
        ],
        [
            Paragraph("Direct Relevance", body_style),
            "20",
            f"{breakdown.get('direct_relevance', 0)}",
            f"-{points_lost_by_crit.get('direct_relevance', round(max(0.0, 20.0 - breakdown.get('direct_relevance', 0)), 1))}"
        ],
        [
            Paragraph("Recency", body_style),
            "15",
            f"{breakdown.get('recency', 0)}",
            f"-{points_lost_by_crit.get('recency', round(max(0.0, 15.0 - breakdown.get('recency', 0)), 1))}"
        ],
        [
            Paragraph("Contradiction Handling", body_style),
            "10",
            f"{breakdown.get('contradiction_handling', 0)}",
            f"-{points_lost_by_crit.get('contradiction_handling', round(max(0.0, 10.0 - breakdown.get('contradiction_handling', 0)), 1))}"
        ],
        [
            Paragraph("<b>Overall Score</b>", table_header_style),
            Paragraph("<b>100</b>", table_header_style),
            Paragraph(f"<b>{evidence_strength.overall_score} / 100</b>", table_header_style),
            Paragraph(f"<b>-{max(0, 100 - evidence_strength.overall_score)}</b>", table_header_style),
        ]
    ]
    rubric_table = Table(rubric_data, colWidths=[160, 60, 70, 70])
    rubric_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F1F5F9')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#EFF6FF'))
    ]))

    score_box_data = [
        [Paragraph(f"{evidence_strength.overall_score} / 100", score_big_style)],
        [Paragraph(f"<b>{escape_pdf_text(evidence_strength.label.upper())}</b>", ParagraphStyle('ScoreLabel', fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor('#475569'), alignment=1))],
        [Paragraph(
            f"{evidence_strength.verified_claims_count} Verified &nbsp;|&nbsp; "
            f"{evidence_strength.partially_supported_count} Partial &nbsp;|&nbsp; "
            f"{evidence_strength.disputed_claims_count} Disputed &nbsp;|&nbsp; "
            f"{evidence_strength.unverified_claims_count} Unverified",
            ParagraphStyle('Sub', fontName='Helvetica', fontSize=7.5, textColor=colors.HexColor('#64748B'), alignment=1)
        )]
    ]
    score_table = Table(score_box_data, colWidths=[170])
    score_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#93C5FD')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5)
    ]))

    assessment_table = Table([[score_table, rubric_table]], colWidths=[175, 365])
    assessment_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(assessment_table)
    story.append(Spacer(1, 3))
    story.append(Paragraph(f"<i>Note: {escape_pdf_text(evidence_strength.explanation)}</i>", ParagraphStyle('Note', fontName='Helvetica-Oblique', fontSize=7.5, textColor=colors.HexColor('#64748B'))))
    story.append(Spacer(1, 8))

    # 4. Executive Summary (Item 10)
    story.append(Paragraph("<b>3. Executive Summary:</b>", h2_style))
    for p in executive_summary.split("\n"):
        if p.strip():
            story.append(Paragraph(escape_pdf_text(p.strip()), body_style))
            story.append(Spacer(1, 2))
    story.append(Spacer(1, 6))

    # Partition claims for Separate Sections (Item 9)
    supported_claims = [
        c for c in claims
        if c.status in (ClaimStatus.VERIFIED, ClaimStatus.PARTIALLY_SUPPORTED)
    ]
    contradicted_unverified_claims = [
        c for c in claims
        if c.status in (ClaimStatus.DISPUTED, ClaimStatus.UNVERIFIED)
    ]

    # 5. Verified & Supported Claims Matrix (Item 8 & 9)
    story.append(Paragraph("<b>4. Verified & Supported Claims:</b>", h2_style))
    if supported_claims:
        story.append(_build_claims_table(supported_claims, body_style, table_header_style, is_contradicted_section=False))
    else:
        story.append(Paragraph("<i>No extracted claims achieved Verified or Partially Supported status.</i>", body_style))
    story.append(Spacer(1, 8))

    # 6. Dedicated Contradicted / Unverified Section (Item 9)
    story.append(Paragraph("<b>5. Contradicted / Unverified Claims & Inconsistencies:</b>", h2_style))
    if contradicted_unverified_claims:
        notice_p = Paragraph(
            "<b>Attention:</b> The claims below encountered unresolved contradictory evidence (DISPUTED) "
            "or failed direct evidence corroboration (UNVERIFIED). Review the noted deductions and conflicts.",
            ParagraphStyle('Notice', fontName='Helvetica', fontSize=8, leading=10, textColor=colors.HexColor('#991B1B'))
        )
        notice_box = Table([[notice_p]], colWidths=[540])
        notice_box.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#FEF2F2')),
            ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#FCA5A5')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(notice_box)
        story.append(Spacer(1, 4))
        story.append(_build_claims_table(contradicted_unverified_claims, body_style, table_header_style, is_contradicted_section=True))
    else:
        story.append(Paragraph("<i>No contradicted or unverified claims identified. All examined claims met corroborating criteria.</i>", body_style))
    story.append(Spacer(1, 8))

    # 7. Detailed Synthesis (Item 10)
    story.append(Paragraph("<b>6. Detailed Findings & Synthesis:</b>", h2_style))
    for line in final_synthesis.split("\n"):
        clean_line = line.strip()
        if clean_line.startswith("#"):
            story.append(Paragraph(f"<b>{escape_pdf_text(clean_line.lstrip('#').strip())}</b>", h2_style))
        elif clean_line:
            story.append(Paragraph(escape_pdf_text(clean_line), body_style))
            story.append(Spacer(1, 2))
    story.append(Spacer(1, 6))

    # 8. Traceable Sources & Citations (Item 10)
    story.append(Paragraph("<b>7. Traceable Sources & References:</b>", h2_style))
    if citations:
        for cit in citations:
            story.append(Paragraph(f"• <font color='#2563EB'><u>{escape_pdf_text(cit)}</u></font>", body_style))
            story.append(Spacer(1, 2))
    else:
        story.append(Paragraph("• No external web citations or internal document chunks cited.", body_style))
    story.append(Spacer(1, 6))

    # 9. Limitations & Deductions Log (Item 7 & 10)
    story.append(Paragraph("<b>8. Disclosed Limitations & Deduction Audit:</b>", h2_style))
    combined_notes = []
    if limitations:
        for lim in limitations:
            combined_notes.append(lim)
    if evidence_strength.deductions:
        for d in evidence_strength.deductions:
            if d not in combined_notes:
                combined_notes.append(d)

    if combined_notes:
        for n in combined_notes[:10]:
            story.append(Paragraph(f"• {escape_pdf_text(n)}", body_style))
            story.append(Spacer(1, 2))
    else:
        story.append(Paragraph("• No significant evidence gaps or deductions recorded.", body_style))

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
