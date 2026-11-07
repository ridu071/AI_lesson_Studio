"""Student downloads: the full notes as a PDF, and a one-page summary image.

Both are built from the stored lesson (no AI call), so they always match what
was quality-checked. Visuals become tables or arrow lists in the PDF, because
graph drawings need a browser.
"""

import io
import re
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (KeepTogether, ListFlowable, ListItem, PageBreak, Paragraph, Preformatted,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

from app.schemas.enums import AssessmentKind, ContentBlockType, QuestionType, SectionType, SourceType, VisualType
from app.schemas.lesson import ContentBlock, LessonVersion
from app.schemas.research import ResearchPackage

GREEN, DEEP, MINT, STONE, AMBER = "#047857", "#064E3B", "#F0FDF4", "#57534E", "#F59E0B"

_FONT_CANDIDATES = [  # (regular, bold): Windows, Linux, macOS
    ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
]


def find_fonts() -> tuple[str, str] | None:
    """A TrueType font that covers accents, Greek letters and arrows, if the system has one."""
    return next(((r, b) for r, b in _FONT_CANDIDATES if Path(r).exists() and Path(b).exists()), None)


def clean(text: str) -> str:
    """Remove emoji and variation selectors (no font in a PDF draws them)."""
    return re.sub(r"[\U0001F000-\U0001FFFF\u2600-\u27BF\uFE0F\u200D]", "", text or "").strip()


# ----------------------------------------------------------- summary points


def summary_points(lesson: LessonVersion) -> dict[str, list[str]]:
    """Key takeaways, common mistakes and next steps, taken from the lesson's Recap."""
    recap = next((s for s in lesson.sections if s.section_type is SectionType.SUMMARY), None)
    takeaways, mistakes, next_steps = [], [], []
    if recap:
        expecting_next = False
        for block in recap.content_blocks:
            if block.type is ContentBlockType.TAKEAWAY and "next" in block.content.lower():
                expecting_next = True
                continue
            if block.type is ContentBlockType.BULLETS:
                (next_steps if expecting_next else takeaways).extend(block.items)
                expecting_next = False
            elif block.type is ContentBlockType.CALLOUT and (block.label or "").lower().startswith("common"):
                mistakes.append(block.content)
            elif block.type in (ContentBlockType.EXPLANATION, ContentBlockType.TAKEAWAY) and not takeaways:
                takeaways.append(block.content)
    if not takeaways:  # older lessons: use each section's first takeaway or explanation
        for s in lesson.sections:
            first = next((b.content for b in s.content_blocks
                          if b.type in (ContentBlockType.TAKEAWAY, ContentBlockType.EXPLANATION)), None)
            if first and s.section_type is not SectionType.LEARNING_OBJECTIVES:
                takeaways.append(first)
    return {"takeaways": takeaways[:5], "mistakes": mistakes[:2], "next_steps": next_steps[:3]}


# --------------------------------------------------------------------- PDF


def _styles(regular: str, bold: str) -> dict[str, ParagraphStyle]:
    base = dict(fontName=regular, fontSize=10.5, leading=15, textColor=colors.HexColor("#1C1917"), alignment=TA_LEFT)
    return {
        "title": ParagraphStyle("title", **(base | dict(fontName=bold, fontSize=22, leading=27,
                                                        textColor=colors.HexColor(DEEP)))),
        "goal": ParagraphStyle("goal", **(base | dict(fontSize=11.5, leading=16, textColor=colors.HexColor(STONE)))),
        "h2": ParagraphStyle("h2", **(base | dict(fontName=bold, fontSize=15, leading=20, spaceBefore=14,
                                                  spaceAfter=4, textColor=colors.HexColor(DEEP)))),
        "h3": ParagraphStyle("h3", **(base | dict(fontName=bold, fontSize=11.5, leading=16, spaceBefore=6))),
        "body": ParagraphStyle("body", **(base | dict(spaceAfter=5))),
        "takeaway": ParagraphStyle("takeaway", **(base | dict(fontName=bold, textColor=colors.HexColor(DEEP),
                                                              spaceBefore=6, spaceAfter=3))),
        "caption": ParagraphStyle("caption", **(base | dict(fontSize=9, leading=12, textColor=colors.HexColor(STONE),
                                                            spaceAfter=8))),
        "small": ParagraphStyle("small", **(base | dict(fontSize=9, leading=12, textColor=colors.HexColor(STONE)))),
        "code": ParagraphStyle("code", **(base | dict(fontName="Courier", fontSize=9, leading=12))),
    }


def _p(text: str, style) -> Paragraph:
    return Paragraph(escape(clean(text)), style)


def _bullets(items: list[str], style) -> ListFlowable:
    return ListFlowable([ListItem(_p(i, style), leftIndent=12) for i in items], bulletType="bullet",
                        start="•", leftIndent=12, bulletFontSize=9)


def _box(flowables: list, fill: str, edge: str) -> Table:
    table = Table([[flowables]], colWidths=[170 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(fill)),
        ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor(edge)),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def _data_table(rows: list[list[str]], st: dict) -> Table:
    width = max(len(r) for r in rows)
    data = [[_p(c, st["small"]) for c in r] + [""] * (width - len(r)) for r in rows]
    table = Table(data, colWidths=[170 * mm / width] * width, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCFCE7")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D6D3D1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def _visual(block: ContentBlock, st: dict) -> list:
    vt = block.visual_type
    out: list = []
    if vt in (VisualType.TABLE, VisualType.CHART) and block.rows:
        out.append(_data_table(block.rows, st))
    elif vt is VisualType.CODE_SNIPPET:
        out.append(Preformatted(block.content or "\n".join(block.elements), st["code"]))
        out += [_bullets(block.elements, st["body"])] if block.content and block.elements else []
    elif vt is VisualType.FORMULA_CARD and block.elements:
        out.append(_box([_p(block.elements[0], st["takeaway"])] +
                        ([_bullets(block.elements[1:], st["body"])] if block.elements[1:] else []), MINT, GREEN))
    elif block.connections:  # graphs as "A -> B" steps
        lines = [c.replace("->", "→") for c in block.connections]
        out.append(_box([_bullets(lines, st["body"])], MINT, GREEN))
    elif block.elements:
        out.append(_box([_bullets(block.elements, st["body"])], MINT, GREEN))
    out.append(_p(f"Visual: {block.caption or ''}", st["caption"]))
    return out


def _block(block: ContentBlock, st: dict) -> list:
    kind = block.type
    if kind is ContentBlockType.VISUAL:
        return _visual(block, st)
    if kind is ContentBlockType.TAKEAWAY:
        return [_p(block.content, st["takeaway"])]
    if kind is ContentBlockType.BULLETS:
        return [_bullets(block.items, st["body"])]
    if kind is ContentBlockType.CODE:
        return [Preformatted(block.content, st["code"])]
    if kind is ContentBlockType.CALLOUT:
        label = block.label or "Key idea"
        fill, edge = (("#FEF2F2", "#DC2626") if label.lower().startswith("common")
                      else ("#FFFBEB", AMBER) if label == "Tip" else (MINT, GREEN))
        return [_box([Paragraph(f"<b>{escape(label)}</b> - {escape(clean(block.content))}", st["body"])], fill, edge)]
    if kind is ContentBlockType.DEFINITION:
        return [_box([Paragraph(f"<b>Definition</b> - {escape(clean(block.content))}", st["body"])], MINT, GREEN)]
    if kind is ContentBlockType.EXAMPLE:
        return [_box([Paragraph(f"<b>Example</b> - {escape(clean(block.content))}", st["body"])], "#FFFBEB", AMBER)]
    return [_p(block.content, st["body"])]


def _question(n: int, q, st: dict) -> list:
    parts = [_p(f"{n}. {q.prompt}", st["h3"])]
    if q.visual:
        parts += _visual(q.visual, st)
    if q.options:
        parts.append(_bullets(q.options, st["body"]))
    if q.question_type is QuestionType.ORDER_STEPS:
        parts += [_p("Put these steps in order:", st["small"]), _bullets(sorted(q.correct_order), st["body"])]
    if q.question_type in (QuestionType.MATCH_PAIRS, QuestionType.LABEL_VISUAL):
        parts += [_p("Match:", st["small"]), _bullets([f"{left} = ____" for left, _ in q.pairs], st["body"])]
    if q.hint:
        parts.append(_p(f"Hint: {q.hint}", st["small"]))
    return [KeepTogether(parts), Spacer(1, 4)]


def _answer(q) -> str:
    if q.question_type is QuestionType.ORDER_STEPS:
        return " → ".join(q.correct_order)
    if q.question_type in (QuestionType.MATCH_PAIRS, QuestionType.LABEL_VISUAL):
        return "; ".join(f"{a} = {b}" for a, b in q.pairs)
    return q.answer_key


def lesson_pdf(lesson: LessonVersion, research: ResearchPackage) -> bytes:
    fonts = find_fonts()
    regular, bold = "Helvetica", "Helvetica-Bold"
    if fonts:
        pdfmetrics.registerFont(TTFont("LessonSans", fonts[0]))
        pdfmetrics.registerFont(TTFont("LessonSans-Bold", fonts[1]))
        regular, bold = "LessonSans", "LessonSans-Bold"
    st = _styles(regular, bold)
    minutes = sum(s.duration_minutes for s in lesson.sections)
    story: list = [
        _p(lesson.title, st["title"]),
        _p(f"{lesson.learner_level.capitalize()} · {minutes} minutes · version {lesson.version}", st["small"]),
        Spacer(1, 6),
        _box([_p("By the end of this lesson you will be able to:", st["takeaway"]),
              _bullets([o.description for o in lesson.learning_objectives], st["body"])], MINT, GREEN),
    ]
    questions = [q for q in lesson.assessments]
    number = {q.question_id: n for n, q in enumerate(questions, start=1)}
    for s in lesson.sections:
        if s.section_type is SectionType.LEARNING_OBJECTIVES:
            continue
        story.append(_p(s.title, st["h2"]))
        for block in s.content_blocks:
            story += _block(block, st)
        for a in [a for a in lesson.activities if a.section_id == s.section_id]:
            story += [_p(f"Practice: {a.title}", st["h3"]), _p(a.instructions, st["body"])]
        for q in [q for q in questions if q.section_id == s.section_id]:
            story += _question(number[q.question_id], q, st)

    story += [PageBreak(), _p("Answer key", st["h2"])]
    for q in questions:
        kind = "Test" if q.kind is AssessmentKind.FINAL else "Check"
        story.append(Paragraph(f"<b>{number[q.question_id]}. ({kind})</b> {escape(clean(_answer(q)))} - "
                               f"{escape(clean(q.explanation))}", st["body"]))
    if lesson.videos or research.sources:
        story.append(_p("Videos and references", st["h2"]))
        for v in lesson.videos:
            story.append(Paragraph(f'<b>Video:</b> {escape(clean(v.title))} - '
                                   f'<link href="{escape(str(v.url))}" color="{GREEN}">{escape(str(v.url))}</link>',
                                   st["small"]))
        cited = {sid for s in lesson.sections for sid in s.source_ids} | {sid for c in lesson.claims for sid in c.source_ids}
        for src in research.sources:
            if src.source_id in cited or src.source_type is SourceType.BOOK:
                kind = "Book" if src.source_type is SourceType.BOOK else "Website"
                link = (f' - <link href="{escape(str(src.url))}" color="{GREEN}">{escape(str(src.url))}</link>'
                        if src.url else "")
                story.append(Paragraph(f"<b>{kind}:</b> {escape(clean(src.title))}{link}", st["small"]))

    buffer = io.BytesIO()

    def footer(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont(regular, 8)
        canvas.setFillColor(colors.HexColor(STONE))
        canvas.drawString(20 * mm, 10 * mm, clean(f"{lesson.title} · AI Lesson Studio"))
        canvas.drawRightString(190 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    SimpleDocTemplate(buffer, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm,
                      bottomMargin=18 * mm, title=clean(lesson.title), author="AI Lesson Studio") \
        .build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


# ----------------------------------------------------------- summary image


def _font(size: int, bold: bool = False):
    fonts = find_fonts()
    if fonts:
        return ImageFont.truetype(fonts[1] if bold else fonts[0], size)
    return ImageFont.load_default(size=size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> list[str]:
    lines, line = [], ""
    for word in clean(text).split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    return lines + ([line] if line else [])


def summary_image(lesson: LessonVersion) -> bytes:
    """A 1080x1350 summary card (portrait, shareable): topic, goal, takeaways, mistakes, next steps."""
    W, H, M = 1080, 1350, 70
    img = Image.new("RGB", (W, H), "#F4FBF6")
    d = ImageDraw.Draw(img)
    title_f, head_f, body_f, small_f = _font(58, True), _font(34, True), _font(29), _font(24)

    # Header band
    title_lines = _wrap(d, lesson.title, title_f, W - 2 * M)[:2]
    band = 120 + 70 * len(title_lines)
    d.rectangle([0, 0, W, band], fill=DEEP)
    d.text((M, 50), "LESSON SUMMARY", font=small_f, fill="#A7F3D0")
    y = 90
    for line in title_lines:
        d.text((M, y), line, font=title_f, fill="white")
        y += 70
    y = band + 40

    points = summary_points(lesson)
    goals = [o.description for o in lesson.learning_objectives]

    def mark(kind: str, x: int, top: int, colour: str) -> None:
        """Draw the bullet marker as a shape, so it never depends on font coverage."""
        cy = top + 20
        if kind == "ring":
            d.ellipse([x + 4, cy - 10, x + 24, cy + 10], outline=colour, width=4)
        elif kind == "tick":
            d.line([(x + 3, cy), (x + 11, cy + 9), (x + 27, cy - 10)], fill=colour, width=5, joint="curve")
        elif kind == "cross":
            d.line([(x + 5, cy - 9), (x + 23, cy + 9)], fill=colour, width=5)
            d.line([(x + 5, cy + 9), (x + 23, cy - 9)], fill=colour, width=5)
        else:  # arrow
            d.line([(x + 3, cy), (x + 25, cy)], fill=colour, width=4)
            d.polygon([(x + 27, cy), (x + 17, cy - 8), (x + 17, cy + 8)], fill=colour)

    def section(heading: str, items: list[str], marker: str, colour: str) -> None:
        nonlocal y
        if not items or y > H - 220:
            return
        d.text((M, y), heading, font=head_f, fill=DEEP)
        y += 52
        for item in items:
            lines = _wrap(d, item, body_f, W - 2 * M - 50)
            if y + 40 * len(lines) > H - 140:
                return
            mark(marker, M, y, colour)
            for line in lines:
                d.text((M + 45, y), line, font=body_f, fill="#1C1917")
                y += 40
            y += 10
        y += 18

    section("Goal", goals[:3], "ring", GREEN)
    section("Key takeaways", points["takeaways"], "tick", GREEN)
    section("Watch out for", points["mistakes"], "cross", "#DC2626")
    section("Next steps", points["next_steps"], "arrow", AMBER)

    minutes = sum(s.duration_minutes for s in lesson.sections)
    d.line([(M, H - 100), (W - M, H - 100)], fill="#D6D3D1", width=2)
    d.text((M, H - 80), clean(f"{lesson.learner_level.capitalize()} · {minutes}-minute lesson · facts checked against sources"),
           font=small_f, fill=STONE)
    d.text((W - M - d.textlength("AI Lesson Studio", font=small_f), H - 80), "AI Lesson Studio",
           font=small_f, fill=GREEN)
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()
