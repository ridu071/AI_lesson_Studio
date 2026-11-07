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


class AuditType(StrEnum):
    """Which independent QC layer produced an audit or issue."""

    QC1 = "qc1"  # factual accuracy and research verification
    QC2 = "qc2"  # instructional effectiveness and learning alignment


class AuditStatus(StrEnum):
    """Lifecycle of one QC audit (QC1 and QC2 each have their own).

    There are three kinds of status, and they must not be confused:
    - In progress:  PENDING, RUNNING.
    - Outcome:      PASSED, NEEDS_REVISION, MANUAL_REVIEW, BLOCKED.
                    The audit finished and this is its judgement of the lesson.
    - Not a judgement:
        ERROR  the audit could not finish (e.g. a model timeout). It says nothing
               about the lesson. The fix is to retry the same audit.
        STALE  the lesson version changed after this audit ran.
    """

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    NEEDS_REVISION = "needs_revision"
    MANUAL_REVIEW = "manual_review"
    BLOCKED = "blocked"
    ERROR = "error"
    STALE = "stale"


# Statuses that mean "the audit finished and judged the lesson".
AUDIT_OUTCOMES = frozenset(
    {
        AuditStatus.PASSED,
        AuditStatus.NEEDS_REVISION,
        AuditStatus.MANUAL_REVIEW,
        AuditStatus.BLOCKED,
    }
)


class IssueType(StrEnum):
    """Every kind of problem a QC layer can report.

    Fixed types (instead of free text) let the benchmark check that the right
    problem was detected, not just that "some" problem was detected.
    """

    # --- QC1: factual accuracy ---
    UNSUPPORTED_CLAIM = "unsupported_claim"
    PARTIALLY_SUPPORTED_CLAIM = "partially_supported_claim"
    CONTRADICTED_CLAIM = "contradicted_claim"
    UNVERIFIABLE_CLAIM = "unverifiable_claim"
    MISSING_CITATION = "missing_citation"
    FABRICATED_CITATION = "fabricated_citation"
    MISLEADING_CITATION = "misleading_citation"
    INACCESSIBLE_SOURCE = "inaccessible_source"
    LOW_CREDIBILITY_SOURCE = "low_credibility_source"
    OUTDATED_SOURCE = "outdated_source"
    INTERNAL_CONTRADICTION = "internal_contradiction"
    RESEARCH_GAP = "research_gap"

    # --- QC2: instructional quality ---
    OBJECTIVE_NOT_EXPLAINED = "objective_not_explained"
    OBJECTIVE_NOT_EXEMPLIFIED = "objective_not_exemplified"
    OBJECTIVE_NOT_PRACTICED = "objective_not_practiced"
    OBJECTIVE_NOT_ASSESSED = "objective_not_assessed"
    BLOOM_MISMATCH = "bloom_mismatch"
    MISSING_SECTION = "missing_section"
    POOR_SEQUENCING = "poor_sequencing"
    UNCLEAR_EXPLANATION = "unclear_explanation"
    WEAK_EXAMPLE = "weak_example"
    UNCLEAR_ACTIVITY = "unclear_activity"
    WEAK_ASSESSMENT = "weak_assessment"
    INCORRECT_ANSWER_KEY = "incorrect_answer_key"
    DURATION_EXCEEDED = "duration_exceeded"
    DURATION_MISMATCH = "duration_mismatch"
    ACCESSIBILITY_ISSUE = "accessibility_issue"


class Evaluator(StrEnum):
    """One unit of QC work. Each audit records which evaluators actually ran,
    so a score is never presented as complete when some checks were skipped.
    """

    # --- QC1 ---
    CITATION_CHECK = "citation_check"  # deterministic (Step 3)
    CLAIM_VERIFICATION = "claim_verification"  # LLM (Step 6)
    CONSISTENCY_CHECK = "consistency_check"  # LLM (Step 6)
    GAP_DETECTION = "gap_detection"  # LLM (Step 6)
    SOURCE_ASSESSMENT = "source_assessment"  # later
    # --- QC2 ---
    STRUCTURE_CHECK = "structure_check"  # deterministic
    DURATION_CHECK = "duration_check"  # deterministic
    COVERAGE_CHECK = "coverage_check"  # deterministic
    ASSESSMENT_CHECK = "assessment_check"  # deterministic
    INSTRUCTIONAL_REVIEW = "instructional_review"  # LLM (Step 6)


_QC1_ISSUES = (
    IssueType.UNSUPPORTED_CLAIM,
    IssueType.PARTIALLY_SUPPORTED_CLAIM,
    IssueType.CONTRADICTED_CLAIM,
    IssueType.UNVERIFIABLE_CLAIM,
    IssueType.MISSING_CITATION,
    IssueType.FABRICATED_CITATION,
    IssueType.MISLEADING_CITATION,
    IssueType.INACCESSIBLE_SOURCE,
    IssueType.LOW_CREDIBILITY_SOURCE,
    IssueType.OUTDATED_SOURCE,
    IssueType.INTERNAL_CONTRADICTION,
    IssueType.RESEARCH_GAP,
)

# Which layer is allowed to report each issue type. Keeps QC1 and QC2 independent:
# QC1 cannot raise a teaching issue and QC2 cannot raise a factual one.
ISSUE_TYPE_OWNER: dict[IssueType, AuditType] = {
    t: (AuditType.QC1 if t in _QC1_ISSUES else AuditType.QC2) for t in IssueType
}


class ReleaseDecision(StrEnum):
    """Final combined outcome. Note: ELIGIBLE is not APPROVED.
    Only the instructor can approve and publish."""

    ELIGIBLE = "eligible_for_instructor_review"
    REVISION_REQUIRED = "revision_required"
    MANUAL_REVIEW = "manual_review"
    BLOCKED = "blocked"
