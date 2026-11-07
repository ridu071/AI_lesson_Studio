from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.modules.qc.enums import AuditStatus, ClaimVerdict, ReleaseDecision
from app.modules.qc.schemas import (
    AuditReport,
    ClaimAssessment,
    ObjectiveCoverage,
    QCInput,
    QCIssue,
    ReleaseResult,
    SubScore,
    weighted_score,
)

HASH = "a" * 64
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)


def issue(**overrides) -> dict:
    data = {
        "issue_id": "QC1-001",
        "audit_type": "qc1",
        "issue_type": "unsupported_claim",
        "severity": "medium",
        "explanation": "No passage in the research package supports this claim.",
        "claim_id": "CL-004",
    }
    return data | overrides


def subscores() -> list[dict]:
    return [
        {"name": "claim_evidence_support", "weight": 0.6, "score": 90},
        {"name": "source_credibility", "weight": 0.4, "score": 80},
    ]  # weighted score = 86.0


def audit(**overrides) -> dict:
    data = {
        "audit_id": "AUD-QC1-001",
        "audit_type": "qc1",
        "lesson_id": "LES-001",
        "version": 1,
        "content_hash": HASH,
        "rubric_version": "0.1.0",
        "status": "passed",
        "score": 86.0,
        "subscores": subscores(),
        "started_at": NOW,
        "completed_at": NOW,
    }
    return data | overrides


# --- input ---


def test_qc_input_accepts_the_fixtures(lesson_data, research_data):
    qc_input = QCInput(
        request_objective="Differentiate supervised and unsupervised learning",
        lesson=lesson_data,
        research=research_data,
    )
    assert qc_input.lesson.version == 1


# --- issues ---


def test_issue_type_must_belong_to_the_reporting_layer():
    with pytest.raises(ValidationError, match="belongs to qc2"):
        QCIssue(**issue(issue_type="objective_not_assessed"))


def test_issue_id_prefix_must_match_layer():
    with pytest.raises(ValidationError, match="prefix"):
        QCIssue(**issue(issue_id="QC2-001"))


def test_critical_or_hard_gate_issues_block_release():
    assert QCIssue(**issue(severity="critical")).blocks_release
    assert QCIssue(**issue(severity="low", hard_gate=True)).blocks_release
    assert not QCIssue(**issue(severity="high")).blocks_release


# --- evidence before confidence ---


def test_supported_verdict_requires_an_evidence_passage():
    with pytest.raises(ValidationError, match="must cite at least one evidence passage"):
        ClaimAssessment(
            claim_id="CL-001",
            verdict=ClaimVerdict.SUPPORTED,
            evidence=[{"source_id": "SRC-001"}],  # source named, but no passage
            explanation="The model is confident this is correct.",
        )


def test_supported_verdict_with_passage_is_accepted():
    a = ClaimAssessment(
        claim_id="CL-001",
        verdict=ClaimVerdict.SUPPORTED,
        evidence=[{"source_id": "SRC-001", "passage_id": "EV-001"}],
        explanation="EV-001 states the same definition.",
    )
    assert a.verdict is ClaimVerdict.SUPPORTED


def test_unsupported_verdict_needs_no_evidence():
    a = ClaimAssessment(
        claim_id="CL-004",
        verdict=ClaimVerdict.UNSUPPORTED,
        explanation="No passage discusses this claim.",
    )
    assert a.evidence == []


# --- scoring ---


def test_weighted_score():
    assert weighted_score([SubScore(**s) for s in subscores()]) == 86.0
    assert weighted_score([]) is None


def test_score_must_match_subscores():
    with pytest.raises(ValidationError, match="score must equal the weighted subscores"):
        AuditReport(**audit(score=99.0))


def test_weights_must_sum_to_one():
    bad = subscores()
    bad[0]["weight"] = 0.5
    with pytest.raises(ValidationError, match="weights must sum to 1"):
        AuditReport(**audit(subscores=bad, score=77.0))


# --- audit status rules ---


def test_passed_audit_is_accepted():
    report = AuditReport(**audit(issues=[issue(severity="low")]))
    assert report.status is AuditStatus.PASSED
    assert report.blocking_issues() == []


@pytest.mark.parametrize(
    "bad_issue",
    [
        issue(severity="high"),
        issue(severity="critical"),
        issue(severity="low", hard_gate=True),
        issue(severity="low", requires_manual_review=True),
    ],
)
def test_passed_audit_cannot_hide_a_serious_issue(bad_issue):
    # The core rule: a high score can never conceal a serious failure.
    with pytest.raises(ValidationError, match="passed audit cannot contain"):
        AuditReport(**audit(issues=[bad_issue]))


def test_blocked_audit_with_high_score_is_allowed():
    # Score 86 but blocked: score and release eligibility are separate.
    report = AuditReport(
        **audit(status="blocked", issues=[issue(issue_type="fabricated_citation", severity="critical")])
    )
    assert report.score == 86.0
    assert len(report.blocking_issues()) == 1


def test_error_audit_must_explain_itself():
    with pytest.raises(ValidationError, match="error_message"):
        AuditReport(**audit(status="error", score=None, subscores=[]))


def test_error_audit_needs_no_score():
    report = AuditReport(
        **audit(status="error", score=None, subscores=[], error_message="Model timed out")
    )
    assert report.score is None


def test_finished_audit_needs_subscores():
    with pytest.raises(ValidationError, match="must include its subscores"):
        AuditReport(**audit(score=None, subscores=[]))


def test_issue_from_other_layer_is_rejected_in_audit():
    qc2_issue = issue(
        issue_id="QC2-001", audit_type="qc2", issue_type="weak_example", claim_id=None
    )
    with pytest.raises(ValidationError, match="qc2 issue inside a qc1 audit"):
        AuditReport(**audit(status="needs_revision", issues=[qc2_issue]))


def test_coverage_belongs_to_qc2_only():
    row = {"objective_id": "LO-01", "explained": True, "exemplified": True,
           "practiced": True, "assessed": True}
    with pytest.raises(ValidationError, match="coverage belongs to QC2 only"):
        AuditReport(**audit(coverage=[row]))
    qc2 = AuditReport(**audit(audit_id="AUD-QC2-001", audit_type="qc2", coverage=[row]))
    assert qc2.coverage[0].is_complete


def test_coverage_row_incomplete_when_any_part_missing():
    row = ObjectiveCoverage(objective_id="LO-02", explained=True, exemplified=True,
                            practiced=False, assessed=True)
    assert not row.is_complete


def test_audit_round_trips_through_json():
    report = AuditReport(**audit(issues=[issue(severity="low")]))
    again = AuditReport.model_validate_json(report.model_dump_json())
    assert again == report


# --- release decision ---


def release(**overrides) -> dict:
    data = {
        "lesson_id": "LES-001",
        "version": 1,
        "content_hash": HASH,
        "qc1_audit_id": "AUD-QC1-001",
        "qc2_audit_id": "AUD-QC2-001",
        "decision": "eligible_for_instructor_review",
        "reasons": ["Both audits passed and no hard gate failed."],
        "decided_at": NOW,
    }
    return data | overrides


def test_eligible_release_is_accepted():
    assert ReleaseResult(**release()).decision is ReleaseDecision.ELIGIBLE


def test_eligible_release_cannot_have_blocking_issues():
    with pytest.raises(ValidationError, match="eligible lesson cannot have blocking issues"):
        ReleaseResult(**release(blocking_issue_ids=["QC1-001"]))


def test_blocked_release_must_name_its_blockers():
    with pytest.raises(ValidationError, match="must name the issues"):
        ReleaseResult(**release(decision="blocked"))


def test_every_decision_needs_a_reason():
    with pytest.raises(ValidationError):
        ReleaseResult(**release(reasons=[]))


def test_naive_timestamps_are_rejected():
    # Times without a timezone are ambiguous in an audit trail.
    with pytest.raises(ValidationError):
        ReleaseResult(**release(decided_at=datetime(2026, 11, 7, 12, 0)))


# --- "not evaluated" is never presented as a score ---


def partial_subscores() -> list[dict]:
    return [
        {"name": "claim_evidence_support", "weight": 0.6, "score": 90},
        {"name": "source_credibility", "weight": 0.4, "score": None},  # not evaluated
    ]


def test_partial_subscores_give_no_score():
    assert weighted_score([SubScore(**s) for s in partial_subscores()]) is None
    report = AuditReport(**audit(status="manual_review", score=None, subscores=partial_subscores()))
    assert report.score is None


def test_partial_subscores_cannot_carry_a_score():
    with pytest.raises(ValidationError, match="score must be empty"):
        AuditReport(**audit(status="manual_review", score=54.0, subscores=partial_subscores()))


def test_passed_audit_needs_every_category_evaluated():
    with pytest.raises(ValidationError, match="every category evaluated"):
        AuditReport(**audit(score=None, subscores=partial_subscores()))


def test_blocking_issue_forces_blocked_status():
    critical = issue(issue_type="fabricated_citation", severity="critical")
    with pytest.raises(ValidationError, match="must be blocked, not needs_revision"):
        AuditReport(**audit(status="needs_revision", issues=[critical]))


def test_blocked_status_needs_a_blocking_issue():
    with pytest.raises(ValidationError, match="must contain a blocking issue"):
        AuditReport(**audit(status="blocked", issues=[issue(severity="high")]))
