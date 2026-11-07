"""Runs all QC1 checks that do not need an LLM."""

from dataclasses import dataclass

from app.modules.qc.enums import AuditType, Evaluator
from app.modules.qc.issues import IssueCollector
from app.modules.qc.qc1.citations import check_citations
from app.modules.qc.schemas import QCInput, QCIssue


EVALUATORS = frozenset({Evaluator.CITATION_CHECK})


@dataclass(frozen=True)
class QC1CheckResult:
    issues: list[QCIssue]
    evaluators: frozenset[Evaluator] = EVALUATORS


def run_qc1_checks(qc_input: QCInput) -> QC1CheckResult:
    issues = IssueCollector(AuditType.QC1)
    check_citations(qc_input.lesson, qc_input.research, issues)
    return QC1CheckResult(issues=issues.issues)
