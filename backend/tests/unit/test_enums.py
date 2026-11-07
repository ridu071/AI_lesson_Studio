from app.modules.qc.enums import (
    AUDIT_OUTCOMES,
    ISSUE_TYPE_OWNER,
    AuditStatus,
    AuditType,
    ClaimVerdict,
    IssueType,
    ReleaseDecision,
    Severity,
    severity_rank,
)


def test_claim_verdicts_match_the_spec_exactly():
    assert {v.value for v in ClaimVerdict} == {
        "supported",
        "partially_supported",
        "contradicted",
        "unsupported",
        "unverifiable",
        "not_applicable",
    }


def test_severity_ordering_critical_is_highest():
    ordered = sorted(Severity, key=severity_rank, reverse=True)
    assert ordered == [
        Severity.CRITICAL,
        Severity.HIGH,
        Severity.MEDIUM,
        Severity.LOW,
    ]


def test_audit_status_values_match_the_spec_exactly():
    assert {s.value for s in AuditStatus} == {
        "pending",
        "running",
        "passed",
        "needs_revision",
        "manual_review",
        "blocked",
        "error",
        "stale",
    }


def test_audit_status_has_no_ambiguous_failed():
    # "failed" could mean "the lesson failed" or "the audit crashed".
    # We use BLOCKED / NEEDS_REVISION for the lesson and ERROR for the audit.
    assert "FAILED" not in {s.name for s in AuditStatus}


def test_error_and_stale_are_not_outcomes():
    # ERROR and STALE say nothing about lesson quality, so they must never be
    # treated as a judgement of the lesson.
    assert AuditStatus.ERROR not in AUDIT_OUTCOMES
    assert AuditStatus.STALE not in AUDIT_OUTCOMES
    assert AUDIT_OUTCOMES == {
        AuditStatus.PASSED,
        AuditStatus.NEEDS_REVISION,
        AuditStatus.MANUAL_REVIEW,
        AuditStatus.BLOCKED,
    }


def test_every_issue_type_belongs_to_exactly_one_layer():
    assert set(ISSUE_TYPE_OWNER) == set(IssueType)
    assert ISSUE_TYPE_OWNER[IssueType.FABRICATED_CITATION] is AuditType.QC1
    assert ISSUE_TYPE_OWNER[IssueType.CONTRADICTED_CLAIM] is AuditType.QC1
    assert ISSUE_TYPE_OWNER[IssueType.OBJECTIVE_NOT_ASSESSED] is AuditType.QC2
    assert ISSUE_TYPE_OWNER[IssueType.DURATION_EXCEEDED] is AuditType.QC2


def test_release_decision_has_no_approved_state():
    # Approval is an instructor action, so the QC engine must not be able to produce it.
    names = {d.name for d in ReleaseDecision}
    assert "APPROVED" not in names
    assert "PUBLISHED" not in names
    assert names == {"ELIGIBLE", "REVISION_REQUIRED", "MANUAL_REVIEW", "BLOCKED"}


def test_enums_compare_equal_to_plain_strings():
    # StrEnum makes JSON and database storage painless.
    assert ClaimVerdict.SUPPORTED == "supported"
