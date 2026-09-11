"""Generate the synthetic, non-private PDF fixtures used by Gate 2 stories."""

from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "public" / "fixtures"
SOURCE_PATH = FIXTURE_DIR / "claros-biology-short-answer.pdf"
COMPLETED_PATH = FIXTURE_DIR / "claros-biology-short-answer-completed.pdf"

INK = HexColor("#172033")
MUTED = HexColor("#59657A")
LINE = HexColor("#CBD5E1")
BLUE = HexColor("#075EE8")
BLUE_SOFT = HexColor("#EEF5FF")

QUESTIONS = (
    (
        "1",
        "Why do plants need sunlight?",
        "Use evidence from the lesson in one or two sentences.",
        560,
        86,
    ),
    (
        "2",
        "How does sunlight help a plant make food?",
        "Describe the role of sunlight in your own words.",
        400,
        86,
    ),
    (
        "3",
        "How can photosynthesis support other living things?",
        "Give one clear connection to another living thing.",
        240,
        52,
    ),
)

ANSWERS = {
    "1": "Plants need sunlight because it helps them make their food.",
}


def draw_wrapped(
    canvas: Canvas,
    text: str,
    x: float,
    y: float,
    max_width: float,
    *,
    font: str = "Helvetica",
    size: float = 10,
    leading: float = 14,
) -> float:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and canvas.stringWidth(candidate, font, size) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    canvas.setFont(font, size)
    for line in lines:
        canvas.drawString(x, y, line)
        y -= leading
    return y


def draw_source_page(canvas: Canvas, answers: dict[str, str] | None = None) -> None:
    width, height = letter
    canvas.setFillColor(HexColor("#FFFFFF"))
    canvas.rect(0, 0, width, height, fill=1, stroke=0)

    canvas.setFillColor(BLUE)
    canvas.roundRect(36, height - 60, 152, 24, 12, fill=1, stroke=0)
    canvas.setFillColor(HexColor("#FFFFFF"))
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawCentredString(112, height - 51, "BIOLOGY • SHORT ANSWER")

    canvas.setFillColor(INK)
    canvas.setFont("Helvetica-Bold", 22)
    canvas.drawString(36, height - 96, "Photosynthesis and plant cells")
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 9)
    canvas.drawRightString(width - 36, height - 48, "Name ____________________")
    canvas.drawRightString(width - 36, height - 64, "Date _____________________")
    canvas.setFont("Helvetica", 10)
    canvas.drawString(
        36,
        height - 121,
        "Directions: Answer each question in your own words. Complete sentences are welcome.",
    )
    canvas.setStrokeColor(LINE)
    canvas.line(36, height - 136, width - 36, height - 136)

    for number, prompt, instruction, top, answer_height in QUESTIONS:
        canvas.setFillColor(BLUE_SOFT)
        canvas.circle(49, top + 8, 13, fill=1, stroke=0)
        canvas.setFillColor(BLUE)
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawCentredString(49, top + 4, number)
        canvas.setFillColor(INK)
        canvas.setFont("Helvetica-Bold", 13)
        canvas.drawString(72, top + 4, prompt)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 9)
        canvas.drawString(72, top - 14, instruction)

        box_top = top - 32
        canvas.setFillColor(HexColor("#FCFDFE"))
        canvas.setStrokeColor(LINE)
        canvas.roundRect(
            72,
            box_top - answer_height,
            width - 108,
            answer_height,
            6,
            fill=1,
            stroke=1,
        )
        for line_y in range(int(box_top - 24), int(box_top - answer_height + 8), -22):
            canvas.setStrokeColor(HexColor("#E7ECF3"))
            canvas.line(84, line_y, width - 48, line_y)
        if answers and number in answers:
            canvas.setFillColor(INK)
            draw_wrapped(
                canvas,
                answers[number],
                84,
                box_top - 20,
                width - 144,
                font="Helvetica",
                size=10,
                leading=15,
            )

    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(36, 24, "Synthetic Claros fixture • no private student data")
    canvas.drawRightString(width - 36, 24, "Page 1 of 1")


def build_source() -> None:
    canvas = Canvas(str(SOURCE_PATH), pagesize=letter, pageCompression=0, invariant=1)
    canvas.setTitle("Claros Biology Short Answer Fixture")
    draw_source_page(canvas)
    canvas.showPage()
    canvas.save()


def build_completed() -> None:
    canvas = Canvas(str(COMPLETED_PATH), pagesize=letter, pageCompression=0, invariant=1)
    canvas.setTitle("Claros Biology Short Answer Fixture — Completed")
    draw_source_page(canvas, ANSWERS)
    canvas.showPage()
    canvas.save()


if __name__ == "__main__":
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    build_source()
    build_completed()
