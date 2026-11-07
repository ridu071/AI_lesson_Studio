"""Runs all QC1 checks that do not need an LLM."""

from app.modules.qc.enums import AuditType
from app.modules.qc.issues import IssueCollector
from app.modules.qc.qc1.citations import check_citations
from app.modules.qc.schemas import QCInput, QCIssue


def run_qc1_checks(qc_input: QCInput) -> list[QCIssue]:
    issues = IssueCollector(AuditType.QC1)
    check_citations(qc_input.lesson, qc_input.research, issues)
    return issues.issues
