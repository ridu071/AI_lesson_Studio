"""The objective coverage matrix (workflow section 7.3).

For each learning objective:
- explained:   a concept_explanation section is mapped to it
- exemplified: a worked_examples section, or a section with an example block, is mapped to it
- practiced:   a mandatory activity, OR a question at the apply level or higher, is mapped to it
               (lessons without practice tasks practise through applied test questions)
- assessed:    a FINAL assessment question is mapped to it (knowledge checks
               alone do not count: the final assessment is what measures the objective)

This checks the lesson's declared mapping. Whether the content really teaches
the objective well is judged by the LLM evaluators in Step 6.
"""

from app.modules.qc.enums import IssueType
from app.modules.qc.issues import IssueCollector
from app.modules.qc.schemas import ObjectiveCoverage
from app.schemas.enums import AssessmentKind, BloomLevel, ContentBlockType, SectionType, bloom_rank
from app.schemas.lesson import LessonVersion


def build_coverage(lesson: LessonVersion) -> list[ObjectiveCoverage]:
    rows = []
    for objective in lesson.learning_objectives:
        oid = objective.id
        sections = [s for s in lesson.sections if oid in s.objective_ids]
        rows.append(
            ObjectiveCoverage(
                objective_id=oid,
                explained=any(s.section_type is SectionType.CONCEPT_EXPLANATION for s in sections),
                exemplified=any(
                    s.section_type is SectionType.WORKED_EXAMPLES
                    or any(b.type is ContentBlockType.EXAMPLE for b in s.content_blocks)
                    for s in sections
                ),
                practiced=any(
                    a.is_mandatory and oid in a.objective_ids for a in lesson.activities
                ) or any(
                    oid in q.objective_ids and bloom_rank(q.bloom_level) >= bloom_rank(BloomLevel.APPLY)
                    for q in lesson.assessments
                ),
                assessed=any(
                    q.kind is AssessmentKind.FINAL and oid in q.objective_ids
                    for q in lesson.assessments
                ),
            )
        )
    return rows


# (coverage field, issue type, what is missing, recommended action)
_GAPS = (
    ("explained", IssueType.OBJECTIVE_NOT_EXPLAINED, "explained in a concept section",
     "Add an explanation of this objective in a concept_explanation section."),
    ("exemplified", IssueType.OBJECTIVE_NOT_EXEMPLIFIED, "illustrated with an example",
     "Add a worked example for this objective."),
    ("practiced", IssueType.OBJECTIVE_NOT_PRACTICED,
     "practised (no mandatory activity and no question at the apply level or above)",
     "Add a practical activity or an applied question for this objective."),
    ("assessed", IssueType.OBJECTIVE_NOT_ASSESSED, "tested in the final assessment",
     "Add a final assessment question that tests this objective."),
)


def check_coverage(coverage: list[ObjectiveCoverage], issues: IssueCollector) -> None:
    for row in coverage:
        for field, issue_type, missing, action in _GAPS:
            if not getattr(row, field):
                issues.add(
                    issue_type,
                    f"Objective {row.objective_id} is never {missing}.",
                    objective_id=row.objective_id,
                    recommendation=action,
                )
