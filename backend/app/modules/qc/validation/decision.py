"""The release decision rule (docs/qc_specification.md section 5).

Applied in order; the first match wins:
  1. any critical or hard-gate issue                         -> BLOCKED
  2. any manual-review issue, or any category not evaluated  -> MANUAL_REVIEW
  3. any high issue, or score below threshold                -> NEEDS_REVISION
  4. otherwise                                               -> PASSED

The combined release decision is the worse of the two audit outcomes.
"""

from collections.abc import Sequence
from datetime import datetime

from app.modules.qc.enums import (
    AUDIT_OUTCOMES,
    AuditStatus,
    AuditType,
    ReleaseDecision,
    Severity,
)
from app.modules.qc.schemas import AuditReport, QCIssue, ReleaseResult, SubScore
from app.schemas.lesson import LessonVersion

# Worst first.
_OUTCOME_PRIORITY = (
    AuditStatus.BLOCKED,
    AuditStatus.MANUAL_REVIEW,
    AuditStatus.NEEDS_REVISION,
    AuditStatus.PASSED,
)

_DECISION_FOR = {
    AuditStatus.BLOCKED: ReleaseDecision.BLOCKED,
    AuditStatus.MANUAL_REVIEW: ReleaseDecision.MANUAL_REVIEW,
    AuditStatus.NEEDS_REVISION: ReleaseDecision.REVISION_REQUIRED,
    AuditStatus.PASSED: ReleaseDecision.ELIGIBLE,
}


class AuditNotReadyError(Exception):
    """An audit has no outcome yet (pending, running, error or stale). Rerun it first."""


class AuditMismatchError(Exception):
    """An audit does not belong to the exact lesson version being decided."""


def audit_outcome(
    issues: Sequence[QCIssue],
    subscores: Sequence[SubScore],
    score: float | None,
    min_score: float,
) -> AuditStatus:
    if any(i.blocks_release for i in issues):
        return AuditStatus.BLOCKED
    if any(i.requires_manual_review for i in issues) or not all(s.evaluated for s in subscores):
        return AuditStatus.MANUAL_REVIEW
    if any(i.severity is Severity.HIGH for i in issues) or score is None or score < min_score:
        return AuditStatus.NEEDS_REVISION
    return AuditStatus.PASSED


def is_stale(audit: AuditReport, lesson: LessonVersion) -> bool:
    """True if the audit was not run on exactly this lesson content."""
    return (audit.lesson_id, audit.version, audit.content_hash) != (
        lesson.lesson_id,
        lesson.version,
        lesson.content_hash(),
    )


def _explain(audit: AuditReport) -> list[str]:
    """Plain-language reasons for one audit's outcome."""
    label = audit.audit_type.value.upper()
    if audit.status is AuditStatus.BLOCKED:
        return [
            f"{label} blocked by {i.issue_id} ({i.issue_type}): {i.explanation}"
            for i in audit.blocking_issues()
        ]
    if audit.status is AuditStatus.MANUAL_REVIEW:
        reasons = [
            f"{label} needs human judgement on {i.issue_id} ({i.issue_type}): {i.explanation}"
            for i in audit.issues
            if i.requires_manual_review
        ]
        unevaluated = [s.name for s in audit.subscores if not s.evaluated]
        if unevaluated:
            reasons.append(
                f"{label} categories not evaluated yet (their checks have not run): "
                + ", ".join(unevaluated)
            )
        return reasons
    if audit.status is AuditStatus.NEEDS_REVISION:
        reasons = [
            f"{label} high-severity {i.issue_id} ({i.issue_type}): {i.explanation}"
            for i in audit.issues
            if i.severity is Severity.HIGH
        ]
        return reasons or [f"{label} score {audit.score} is below the pass threshold."]
    return [f"{label} passed with score {audit.score}."]


def decide(
    qc1: AuditReport, qc2: AuditReport, lesson: LessonVersion, *, now: datetime
) -> ReleaseResult:
    """Combine both audits into one release decision for this exact lesson version."""
    if qc1.audit_type is not AuditType.QC1 or qc2.audit_type is not AuditType.QC2:
        raise ValueError("decide() needs a QC1 audit and a QC2 audit, in that order")
    for audit in (qc1, qc2):
        if audit.status not in AUDIT_OUTCOMES:
            raise AuditNotReadyError(
                f"{audit.audit_id} is '{audit.status}'; rerun it before deciding"
            )
        if is_stale(audit, lesson):
            raise AuditMismatchError(
                f"{audit.audit_id} was run on a different version or content of "
                f"{lesson.lesson_id}; rerun QC on version {lesson.version}"
            )

    worst = min((qc1.status, qc2.status), key=_OUTCOME_PRIORITY.index)
    return ReleaseResult(
        lesson_id=lesson.lesson_id,
        version=lesson.version,
        content_hash=lesson.content_hash(),
        qc1_audit_id=qc1.audit_id,
        qc2_audit_id=qc2.audit_id,
        decision=_DECISION_FOR[worst],
        reasons=_explain(qc1) + _explain(qc2),
        blocking_issue_ids=[i.issue_id for a in (qc1, qc2) for i in a.blocking_issues()],
        decided_at=now,
    )
