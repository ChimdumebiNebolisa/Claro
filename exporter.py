"""
PDF export for Claros: generates a PDF with assignment title, questions, and written answers.
"""
from datetime import datetime
from io import BytesIO
from typing import List

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable


def build_export_pdf(
    title: str,
    questions: List[dict],
    answers: List[dict],
) -> bytes:
    """
    Build PDF bytes. questions = [{"id": 1, "text": "..."}], answers = [{"question_id": 1, "answer_text": "..."}].
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        rightMargin=inch,
        leftMargin=inch,
        topMargin=inch,
        bottomMargin=inch,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=12,
    )
    heading_style = ParagraphStyle(
        "QuestionHead",
        parent=styles["Heading2"],
        fontSize=12,
        spaceAfter=6,
    )
    body_style = styles["Normal"]

    story = []
    story.append(Paragraph("Claros — Assignment Answers", title_style))
    story.append(Paragraph(title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), body_style))
    story.append(Spacer(1, 0.25 * inch))

    answer_by_id = {a["question_id"]: a.get("answer_text", "") for a in answers}

    for q in questions:
        qid = q.get("id", 0)
        qtext = (q.get("text") or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        story.append(Paragraph(f"<b>Question {qid}</b>: {qtext}", heading_style))
        ans = (answer_by_id.get(qid) or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
        story.append(Paragraph(ans or "(No answer)", body_style))
        story.append(Spacer(1, 0.15 * inch))
        story.append(HRFlowable(width="100%", thickness=0.5, color="gray"))
        story.append(Spacer(1, 0.2 * inch))

    story.append(Spacer(1, 0.3 * inch))
    story.append(
        Paragraph(
            f"Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            ParagraphStyle("Footer", parent=body_style, fontSize=8, textColor="gray"),
        )
    )

    doc.build(story)
    return buf.getvalue()
