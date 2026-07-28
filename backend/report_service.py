"""PDF report rendering from persisted WoundLens assets and clinician-entered data."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


DISCLAIMER = "AI-generated text summarizes available WoundLens measurements and clinician-provided information. It is not an autonomous diagnosis or prescription."


def _image(path: Path, width: float = 3.35 * inch, height: float = 2.3 * inch) -> Image | Paragraph:
    if path.is_file():
        return Image(str(path), width=width, height=height, kind="proportional")
    return Paragraph("Visualization unavailable", getSampleStyleSheet()["BodyText"])


def create_report(destination: Path, record: dict[str, Any]) -> None:
    styles = getSampleStyleSheet()
    document = SimpleDocTemplate(str(destination), pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    story: list[Any] = [Paragraph("WoundLens Clinical Assessment Report", styles["Title"]), Spacer(1, 8)]
    story.extend([
        Paragraph(f"Patient ID: {record.get('patient_code', record['patient_id'])}", styles["BodyText"]),
        Paragraph(f"Visit date: {record.get('visit_date', record['id'])}", styles["BodyText"]),
        Spacer(1, 12),
    ])
    assets = {name: Path(path) for name, path in record["assets"].items()}
    story.append(Table([
        [_image(assets.get("rgb_roi", Path())), _image(assets.get("thermal", Path()))],
        [_image(assets.get("relative_depth", Path())), _image(assets.get("surface", Path()))],
    ], colWidths=[3.55 * inch, 3.55 * inch], hAlign="CENTER"))
    story.append(Spacer(1, 12))
    metrics = record["analysis"]
    metric_rows = [["Structural measurement", "Value"], ["Detected wound ROI pixels", str(metrics["wound_roi_pixels"])], ["Relative depth range", f"{metrics['relative_depth_range']:.2f}"], ["Mean absolute depth variation", f"{metrics['mean_depth_variation']:.2f}"], ["Depth variation standard deviation", f"{metrics['depth_variation_std']:.2f}"]]
    metric_table = Table(metric_rows, colWidths=[3.8 * inch, 2.8 * inch])
    metric_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9f0ff")), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b9c7dd")), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("PADDING", (0, 0), (-1, -1), 6)]))
    story.extend([Paragraph("Structural Measurements", styles["Heading2"]), metric_table, Spacer(1, 12)])
    if record.get("ai_summary"):
        summary = record["ai_summary"]
        story.append(Paragraph("AI-Assisted Summary", styles["Heading2"]))
        story.append(Paragraph(summary.get("assessment_summary", ""), styles["BodyText"]))
        for finding in summary.get("structural_findings", []) + summary.get("thermal_findings", []) + summary.get("attention_points", []):
            story.append(Paragraph("- " + finding, styles["BodyText"]))
        story.append(Spacer(1, 12))
    if record.get("clinical_plan"):
        story.append(Paragraph("Clinician-Entered Clinical Plan", styles["Heading2"]))
        for label, value in record["clinical_plan"].items():
            story.append(Paragraph(f"<b>{label.replace('_', ' ').title()}:</b> {value or 'Not entered'}", styles["BodyText"]))
        story.append(Spacer(1, 12))
    story.append(Paragraph(DISCLAIMER, styles["Italic"]))
    document.build(story)
