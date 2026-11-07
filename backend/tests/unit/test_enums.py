from app.modules.qc.enums import (
    AuditStatus,
    ClaimVerdict,
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


def test_audit_status_includes_stale():
    assert AuditStatus.STALE.value == "stale"
    assert len(AuditStatus) == 7


def test_release_decision_has_no_approved_state():
    # Approval is an instructor action, so the QC engine must not be able to produce it.
    names = {d.name for d in ReleaseDecision}
    assert "APPROVED" not in names
    assert "PUBLISHED" not in names
    assert names == {"ELIGIBLE", "REVISION_REQUIRED", "MANUAL_REVIEW", "BLOCKED"}


def test_enums_compare_equal_to_plain_strings():
    # StrEnum makes JSON and database storage painless.
    assert ClaimVerdict.SUPPORTED == "supported"
