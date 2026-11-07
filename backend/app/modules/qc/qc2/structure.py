"""Lesson structure and ordering checks.

The template (workflow section 6.2) is flexible, so only the essentials are
required, and the only ordering rules are ones that are always true:
- the introduction comes first;
- an objective is explained before it is exemplified, practised or assessed.
"""

from app.modules.qc.enums import IssueType
from app.modules.qc.issues import IssueCollector
from app.schemas.enums import SectionType
from app.schemas.lesson import LessonVersion

REQUIRED_SECTION_TYPES = (
    SectionType.INTRODUCTION,
    SectionType.CONCEPT_EXPLANATION,
    SectionType.FINAL_ASSESSMENT,
    SectionType.SUMMARY,
)

# Sections that use an objective, so it must already have been explained.
_USES_OBJECTIVE = frozenset(
    {
        SectionType.WORKED_EXAMPLES,
        SectionType.PRACTICAL_APPLICATION,
        SectionType.KNOWLEDGE_CHECK,
        SectionType.FINAL_ASSESSMENT,
    }
)


def check_structure(lesson: LessonVersion, issues: IssueCollector) -> None:
    present = {s.section_type for s in lesson.sections}
    for section_type in REQUIRED_SECTION_TYPES:
        if section_type not in present:
            issues.add(
                IssueType.MISSING_SECTION,
                f"The lesson has no '{section_type}' section.",
                recommendation=f"Add a '{section_type}' section.",
            )

    first = lesson.sections[0]
    if SectionType.INTRODUCTION in present and first.section_type is not SectionType.INTRODUCTION:
        issues.add(
            IssueType.POOR_SEQUENCING,
            f"The lesson starts with '{first.section_type}' instead of the introduction.",
            section_id=first.section_id,
            recommendation="Move the introduction to the start of the lesson.",
        )

    # Where each objective is first explained: objective_id -> (position, section_id)
    explained_at: dict[str, tuple[int, str]] = {}
    for position, section in enumerate(lesson.sections):
        if section.section_type is SectionType.CONCEPT_EXPLANATION:
            for oid in section.objective_ids:
                explained_at.setdefault(oid, (position, section.section_id))

    for position, section in enumerate(lesson.sections):
        if section.section_type not in _USES_OBJECTIVE:
            continue
        for oid in section.objective_ids:
            # Never-explained objectives are reported by the coverage check.
            if oid in explained_at and position < explained_at[oid][0]:
                issues.add(
                    IssueType.POOR_SEQUENCING,
                    f"{section.section_id} ({section.section_type}) uses {oid} before it is "
                    f"explained in {explained_at[oid][1]}.",
                    section_id=section.section_id,
                    objective_id=oid,
                    recommendation=f"Move {section.section_id} after "
                    f"{explained_at[oid][1]}, or explain {oid} earlier.",
                )
