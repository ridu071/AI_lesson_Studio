"""Runs all QC2 checks that do not need an LLM."""

from dataclasses import dataclass

from app.core.config import get_settings
from app.modules.qc.enums import AuditType, Evaluator
from app.modules.qc.issues import IssueCollector
from app.modules.qc.qc2.assessments import check_answer_keys, check_bloom_alignment
from app.modules.qc.qc2.coverage import build_coverage, check_coverage
from app.modules.qc.qc2.duration import check_duration, mandatory_minutes
from app.modules.qc.qc2.structure import check_structure
from app.modules.qc.schemas import ObjectiveCoverage, QCInput, QCIssue


EVALUATORS = frozenset(
    {
        Evaluator.STRUCTURE_CHECK,
        Evaluator.DURATION_CHECK,
        Evaluator.COVERAGE_CHECK,
        Evaluator.ASSESSMENT_CHECK,
    }
)


@dataclass(frozen=True)
class QC2CheckResult:
    issues: list[QCIssue]
    coverage: list[ObjectiveCoverage]
    mandatory_minutes: int
    evaluators: frozenset[Evaluator] = EVALUATORS


def run_qc2_checks(
    qc_input: QCInput, *, max_minutes: int | None = None, issues: IssueCollector | None = None
) -> QC2CheckResult:
    if max_minutes is None:
        max_minutes = get_settings().max_lesson_minutes
    lesson = qc_input.lesson

    issues = issues or IssueCollector(AuditType.QC2)
    check_structure(lesson, issues)
    check_duration(lesson, issues, max_minutes)
    coverage = build_coverage(lesson)
    check_coverage(coverage, issues)
    check_bloom_alignment(lesson, issues)
    check_answer_keys(lesson, issues)

    return QC2CheckResult(
        issues=issues.issues,
        coverage=coverage,
        mandatory_minutes=mandatory_minutes(lesson),
    )
