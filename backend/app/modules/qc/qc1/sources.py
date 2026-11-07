"""Deterministic source credibility check.

Freshness depends on the topic, so outdated sources are judged by the LLM
review (prompts/qc1/llm_review.md, task 4). Together they form the
SOURCE_ASSESSMENT evaluator.
"""

from app.modules.qc.enums import IssueType
from app.modules.qc.issues import IssueCollector
from app.modules.qc.schemas import EvidenceRef
from app.schemas.enums import AuthorityCategory
from app.schemas.lesson import LessonVersion
from app.schemas.research import ResearchPackage

LOW_AUTHORITY = frozenset({AuthorityCategory.COMMUNITY, AuthorityCategory.UNKNOWN})


def check_source_credibility(
    lesson: LessonVersion, research: ResearchPackage, issues: IssueCollector
) -> None:
    # Only sources used as evidence. Supplementary videos are optional extras.
    evidence_ids = {sid for s in lesson.sections for sid in s.source_ids}
    evidence_ids |= {sid for c in lesson.claims for sid in c.source_ids}
    for source_id in sorted(evidence_ids):
        source = research.find_source(source_id)
        if source and source.authority_category in LOW_AUTHORITY:
            issues.add(
                IssueType.LOW_CREDIBILITY_SOURCE,
                f"{source_id} ('{source.title}') has authority category "
                f"'{source.authority_category}', which is not reliable enough on its own.",
                evidence=[EvidenceRef(source_id=source_id)],
                recommendation="Back the content with an academic, official or "
                "educational source, or remove it.",
            )
