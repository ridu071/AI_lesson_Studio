"""Shared vocabulary for the QC engine.

Using enums instead of loose strings means a typo like "suported" is an
immediate error instead of a silent bug.
"""

from enum import StrEnum


class ClaimVerdict(StrEnum):
    """QC1: how a factual claim relates to the evidence."""

    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    CONTRADICTED = "contradicted"
    UNSUPPORTED = "unsupported"
    UNVERIFIABLE = "unverifiable"
    NOT_APPLICABLE = "not_applicable"


class Severity(StrEnum):
    """How serious an issue is. Ordered from most to least serious."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# Higher number = more serious. Lets us compare or sort severities safely.
_SEVERITY_RANK = {
    Severity.CRITICAL: 4,
    Severity.HIGH: 3,
    Severity.MEDIUM: 2,
    Severity.LOW: 1,
}


def severity_rank(severity: Severity) -> int:
    return _SEVERITY_RANK[severity]


class AuditStatus(StrEnum):
    """Lifecycle of one QC audit (QC1 and QC2 each have their own)."""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    NEEDS_REVISION = "needs_revision"
    MANUAL_REVIEW = "manual_review"
    STALE = "stale"  # the lesson version changed after this audit ran


class ReleaseDecision(StrEnum):
    """Final combined outcome. Note: ELIGIBLE is not APPROVED.
    Only the instructor can approve and publish."""

    ELIGIBLE = "eligible_for_instructor_review"
    REVISION_REQUIRED = "revision_required"
    MANUAL_REVIEW = "manual_review"
    BLOCKED = "blocked"
