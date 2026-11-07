"""The 45-minute rule (spec section 7).

- A section's minutes INCLUDE the activities and questions inside it.
- Mandatory content = all sections + mandatory videos.
- Optional videos never count.
"""

from app.modules.qc.enums import IssueType
from app.modules.qc.issues import IssueCollector
from app.schemas.lesson import LessonVersion


def mandatory_minutes(lesson: LessonVersion) -> int:
    sections = sum(s.duration_minutes for s in lesson.sections)
    videos = sum(v.duration_minutes for v in lesson.videos if v.is_mandatory)
    return sections + videos


def check_duration(lesson: LessonVersion, issues: IssueCollector, max_minutes: int) -> None:
    total = mandatory_minutes(lesson)

    if total > max_minutes:
        issues.add(
            IssueType.DURATION_EXCEEDED,
            f"Mandatory content takes {total} minutes, which is over the "
            f"{max_minutes}-minute limit.",
            recommendation=f"Shorten or remove at least {total - max_minutes} minutes of "
            "mandatory content, or make supplementary material optional.",
        )

    if lesson.stated_duration_minutes != total:
        issues.add(
            IssueType.DURATION_MISMATCH,
            f"The lesson states {lesson.stated_duration_minutes} minutes, but its sections "
            f"and mandatory videos add up to {total}.",
            recommendation="Correct the stated duration or the section timings so they agree.",
        )

    for section in lesson.sections:
        inside = sum(
            a.duration_minutes
            for a in lesson.activities
            if a.section_id == section.section_id and a.is_mandatory
        )
        if inside > section.duration_minutes:
            issues.add(
                IssueType.DURATION_MISMATCH,
                f"Mandatory activities in {section.section_id} need {inside} minutes, but the "
                f"section only allows {section.duration_minutes}.",
                section_id=section.section_id,
                recommendation="Give the section more time or shorten its activities.",
            )
