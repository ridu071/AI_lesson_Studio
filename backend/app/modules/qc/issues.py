"""Helper that every QC check uses to report issues."""

from collections.abc import Iterable

from app.modules.qc.enums import AuditType, ClaimVerdict, IssueType, Severity, severity_rank
from app.modules.qc.policy import ISSUE_POLICY
from app.modules.qc.schemas import EvidenceRef, QCIssue, Recommendation


class IssueCollector:
    """Collects the issues of one QC layer.

    - Gives issues sequential IDs (QC1-001, QC1-002, ...).
    - Applies the default severity and hard gate from ISSUE_POLICY.
    - A check may ESCALATE severity but never weaken it, and can never switch a
      hard gate off. This keeps the policy table the single source of truth.
    """

    def __init__(self, audit_type: AuditType) -> None:
        self._audit_type = audit_type
        self._issues: list[QCIssue] = []

    def add(
        self,
        issue_type: IssueType,
        explanation: str,
        *,
        severity: Severity | None = None,
        requires_manual_review: bool = False,
        section_id: str | None = None,
        claim_id: str | None = None,
        objective_id: str | None = None,
        claim_verdict: ClaimVerdict | None = None,
        evidence: Iterable[EvidenceRef] = (),
        recommendation: str | Recommendation | None = None,
    ) -> QCIssue:
        policy = ISSUE_POLICY[issue_type]
        if severity is not None and severity_rank(severity) < severity_rank(policy.severity):
            raise ValueError(
                f"{issue_type} cannot be reported below its policy severity {policy.severity}"
            )
        if isinstance(recommendation, str):
            recommendation = Recommendation(action=recommendation)

        issue = QCIssue(
            issue_id=f"{self._audit_type.value.upper()}-{len(self._issues) + 1:03d}",
            audit_type=self._audit_type,
            issue_type=issue_type,
            severity=severity or policy.severity,
            hard_gate=policy.hard_gate,
            requires_manual_review=requires_manual_review,
            explanation=explanation,
            section_id=section_id,
            claim_id=claim_id,
            objective_id=objective_id,
            claim_verdict=claim_verdict,
            evidence=list(evidence),
            recommendation=recommendation,
        )
        self._issues.append(issue)
        return issue

    @property
    def issues(self) -> list[QCIssue]:
        return list(self._issues)
