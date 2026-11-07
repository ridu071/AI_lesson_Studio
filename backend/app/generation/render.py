"""Renders a lesson as Markdown for preview and export.

The reference list is built by CODE from the research package (sources the
lesson cites, books, videos), never written by the model, so every link in
the lesson is a real link that research actually found.
"""

from app.generation.visuals import visual_markdown
from app.schemas.enums import AssessmentKind, ContentBlockType, SectionType, SourceType
from app.schemas.lesson import LessonVersion
from app.schemas.research import ResearchPackage

_BLOCK_PREFIX = {
    ContentBlockType.DEFINITION: "**Definition:** ",
    ContentBlockType.EXAMPLE: "**Example:** ",
    ContentBlockType.NOTE: "> ",
}


def _block_markdown(block) -> str:
    kind = block.type
    if kind is ContentBlockType.VISUAL:
        return visual_markdown(block)
    if kind is ContentBlockType.CODE:
        return f"```\n{block.content}\n```"
    if kind is ContentBlockType.BULLETS:
        return "\n".join(f"- {item}" for item in block.items)
    if kind is ContentBlockType.TAKEAWAY:
        return f"**{block.content}**"
    if kind is ContentBlockType.CALLOUT:
        return f"> **{block.label or 'Key idea'}:** {block.content}"
    return _BLOCK_PREFIX.get(kind, "") + block.content


def render_lesson_markdown(lesson: LessonVersion, research: ResearchPackage, *,
                           include_answers: bool = True) -> str:
    minutes = sum(s.duration_minutes for s in lesson.sections)
    lines = [
        f"# {lesson.title}",
        "",
        f"*Level: {lesson.learner_level} - Duration: {minutes} minutes (mandatory content) - "
        f"Version {lesson.version}*",
        "",
        "## Learning objectives",
        "",
        *[f"- **{o.id}** {o.description} *({o.bloom_level})*" for o in lesson.learning_objectives],
        "",
    ]
    number = 0
    for section in lesson.sections:
        if section.section_type is SectionType.LEARNING_OBJECTIVES:
            continue
        lines += [f"## {section.title}  *({section.duration_minutes} min)*", ""]
        for block in section.content_blocks:
            lines += [_block_markdown(block), ""]
        for activity in [a for a in lesson.activities if a.section_id == section.section_id]:
            lines += [f"### Practice: {activity.title} ({activity.duration_minutes} min)", "",
                      activity.instructions, ""]
            if activity.hint:
                lines += [f"*Hint:* {activity.hint}", ""]
        for q in [q for q in lesson.assessments if q.section_id == section.section_id]:
            number += 1
            lines += [f"**Q{number}. {q.prompt}**", ""]
            if q.visual:
                lines += [visual_markdown(q.visual), ""]
            lines += [f"- {option}" for option in q.options]
            if q.question_type.value == "order_steps":
                lines += [f"- {step}" for step in sorted(q.correct_order)]  # shuffled for the learner
            if q.question_type.value in ("match_pairs", "label_visual"):
                lines += [f"- {left} = ____" for left, _ in q.pairs]
            if q.options or q.correct_order or q.pairs:
                lines.append("")
            if q.hint:
                lines += [f"*Hint:* {q.hint}", ""]
    if include_answers and lesson.assessments:
        lines += ["## Answer key", ""]
        for n, q in enumerate(lesson.assessments, start=1):
            kind = "test" if q.kind is AssessmentKind.FINAL else "check"
            level = f", {q.level.value}" if q.level else ""
            lines += [f"{n}. ({kind}{level}) **{q.answer_key}** - {q.explanation}"]
            lines += [f"   - Wrong: \"{w.option}\" ({w.misconception_id}) - {w.misconception}" for w in q.wrong_options]
            if q.review_section_id:
                lines.append(f"   - Review: {q.review_section_id}")
        lines.append("")
    if lesson.remedials:
        lines += ["## Review material (shown when a learner scores below 70% on an objective)", ""]
        for r in lesson.remedials:
            lines += [f"### {r.objective_id}: {r.takeaway}", "", visual_markdown(r.visual), ""]
            lines += r.explanation + [""]
            lines += [f"- **Mix-up:** {m.misconception} **Correction:** {m.correction}" for m in r.common_mix_ups]
            lines.append("")
    answered = [a for a in lesson.activities if a.answer]
    if answered:
        lines += ["## Practice answers", ""]
        lines += [f"- **{a.title}:** {a.answer}" for a in answered]
        lines.append("")

    if lesson.videos:
        lines += ["## Supplementary videos (optional, not part of the 45 minutes)", ""]
        for v in lesson.videos:
            length = f" ({v.duration_minutes} min)" if v.duration_minutes else ""
            lines.append(f"- [{v.title}]({v.url}){length}")
        lines.append("")
    lines += render_references(lesson, research)
    return "\n".join(lines) + "\n"


def render_references(lesson: LessonVersion, research: ResearchPackage) -> list[str]:
    cited = {sid for s in lesson.sections for sid in s.source_ids}
    cited |= {sid for c in lesson.claims for sid in c.source_ids}
    lines = ["## References", ""]
    for s in research.sources:
        if s.source_id in cited:
            lines.append(f"- [{s.title}]({s.url}) - retrieved {s.retrieved_at.isoformat()}")
    books = [s for s in research.sources if s.source_type is SourceType.BOOK]
    if books:
        lines += ["", "**Further reading (books; content not reviewed by the tool)**", ""]
        for b in books:
            author = f" - {b.author}" if b.author else ""
            lines.append(f"- [{b.title}]({b.url}){author}")
    videos = [s for s in research.sources if s.source_type is SourceType.VIDEO]
    if videos:
        lines += ["", "**Videos**", ""]
        lines += [f"- [{v.title}]({v.url}) - {v.publisher or 'YouTube'}" for v in videos]
    return lines + [""]
