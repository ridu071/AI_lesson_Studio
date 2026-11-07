from datetime import UTC, datetime

import pytest

from app.modules.qc.engine import build_audit, run_deterministic_qc
from app.modules.qc.enums import AuditStatus, AuditType, Evaluator, IssueType, ReleaseDecision
from app.modules.qc.issues import IssueCollector
from app.modules.qc.schemas import AuditReport
from app.modules.qc.validation.decision import AuditMismatchError, AuditNotReadyError, decide
from tests.helpers import build_qc_input

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
ALL = set(Evaluator)  # pretend every evaluator ran, including the future LLM ones


def audit(qc_input, audit_type, issues=(), evaluators=ALL, min_score=80.0):
    return build_audit(
        audit_type=audit_type,
        qc_input=qc_input,
        issues=list(issues),
        evaluators=evaluators,
        min_score=min_score,
        started_at=NOW,
        completed_at=NOW,
    )


@pytest.fixture
def qc_input(lesson_data, research_data):
    return build_qc_input(lesson_data, research_data)


def qc1_issue(issue_type, **kw):
    c = IssueCollector(AuditType.QC1)
    return c.add(issue_type, "Explanation of the problem.", **kw)


def qc2_issue(issue_type, **kw):
    c = IssueCollector(AuditType.QC2)
    return c.add(issue_type, "Explanation of the problem.", **kw)


# --- the four outcomes, in priority order ---


def test_clean_fully_evaluated_lesson_is_eligible(qc_input):
    result = decide(audit(qc_input, AuditType.QC1), audit(qc_input, AuditType.QC2),
                    qc_input.lesson, now=NOW)
    assert result.decision is ReleaseDecision.ELIGIBLE
    assert result.blocking_issue_ids == []
    assert result.reasons == ["QC1 passed with score 100.0.", "QC2 passed with score 100.0."]


def test_blocker_wins_over_everything(qc_input):
    qc1 = audit(qc_input, AuditType.QC1, [qc1_issue(IssueType.FABRICATED_CITATION)])
    qc2 = audit(qc_input, AuditType.QC2, [qc2_issue(IssueType.UNCLEAR_EXPLANATION)])
    result = decide(qc1, qc2, qc_input.lesson, now=NOW)
    assert qc1.status is AuditStatus.BLOCKED
    assert result.decision is ReleaseDecision.BLOCKED
    assert result.blocking_issue_ids == ["QC1-001"]


def test_high_score_cannot_hide_a_blocker(qc_input):
    # One critical issue costs 50 points in one category; the weighted score stays high.
    qc1 = audit(qc_input, AuditType.QC1, [qc1_issue(IssueType.FABRICATED_CITATION)])
    assert qc1.score >= 90
    assert qc1.status is AuditStatus.BLOCKED


def test_manual_review_issue(qc_input):
    qc1 = audit(qc_input, AuditType.QC1,
                [qc1_issue(IssueType.UNVERIFIABLE_CLAIM, requires_manual_review=True)])
    result = decide(qc1, audit(qc_input, AuditType.QC2), qc_input.lesson, now=NOW)
    assert result.decision is ReleaseDecision.MANUAL_REVIEW


def test_unevaluated_categories_mean_manual_review(qc_input):
    qc2 = audit(qc_input, AuditType.QC2, evaluators={Evaluator.DURATION_CHECK})
    assert qc2.score is None  # no partial score that looks like a real one
    result = decide(audit(qc_input, AuditType.QC1), qc2, qc_input.lesson, now=NOW)
    assert result.decision is ReleaseDecision.MANUAL_REVIEW
    assert any("not evaluated yet" in r and "clarity" in r for r in result.reasons)


def test_high_issue_needs_revision(qc_input):
    qc2 = audit(qc_input, AuditType.QC2, [qc2_issue(IssueType.INCORRECT_ANSWER_KEY)])
    result = decide(audit(qc_input, AuditType.QC1), qc2, qc_input.lesson, now=NOW)
    assert result.decision is ReleaseDecision.REVISION_REQUIRED
    assert "incorrect_answer_key" in result.reasons[1]


def test_score_below_threshold_needs_revision(qc_input):
    # Medium issues never block on their own, but they lower the score.
    qc2 = audit(qc_input, AuditType.QC2, [qc2_issue(IssueType.UNCLEAR_EXPLANATION)],
                min_score=99.0)
    assert qc2.score == 98.5  # clarity 90 x 0.15 weight
    assert qc2.status is AuditStatus.NEEDS_REVISION
    result = decide(audit(qc_input, AuditType.QC1), qc2, qc_input.lesson, now=NOW)
    assert result.decision is ReleaseDecision.REVISION_REQUIRED
    assert "below the pass threshold" in result.reasons[1]


def test_medium_and_low_issues_stay_eligible(qc_input):
    qc2 = audit(qc_input, AuditType.QC2, [qc2_issue(IssueType.WEAK_EXAMPLE)])
    result = decide(audit(qc_input, AuditType.QC1), qc2, qc_input.lesson, now=NOW)
    assert result.decision is ReleaseDecision.ELIGIBLE


# --- version integrity (E2E-009, E2E-016) ---


def test_audit_of_an_edited_lesson_is_rejected(lesson_data, research_data):
    original = build_qc_input(lesson_data, research_data)
    qc1, qc2 = audit(original, AuditType.QC1), audit(original, AuditType.QC2)

    lesson_data["sections"][2]["content_blocks"][0]["content"] += " Edited."
    edited = build_qc_input(lesson_data, research_data).lesson
    with pytest.raises(AuditMismatchError, match="rerun QC"):
        decide(qc1, qc2, edited, now=NOW)


def test_audit_of_an_older_version_is_rejected(lesson_data, research_data):
    original = build_qc_input(lesson_data, research_data)
    qc1, qc2 = audit(original, AuditType.QC1), audit(original, AuditType.QC2)
    lesson_data["version"] = 2
    with pytest.raises(AuditMismatchError):
        decide(qc1, qc2, build_qc_input(lesson_data, research_data).lesson, now=NOW)


def test_error_audit_gives_no_decision(qc_input):
    qc1 = audit(qc_input, AuditType.QC1)
    errored = AuditReport(**(qc1.model_dump() | {
        "status": "error", "score": None, "subscores": [], "error_message": "Model timed out",
    }))
    with pytest.raises(AuditNotReadyError, match="rerun"):
        decide(errored, audit(qc_input, AuditType.QC2), qc_input.lesson, now=NOW)


def test_audits_must_be_given_in_order(qc_input):
    with pytest.raises(ValueError, match="in that order"):
        decide(audit(qc_input, AuditType.QC2), audit(qc_input, AuditType.QC1),
               qc_input.lesson, now=NOW)


# --- the full deterministic run ---


def test_deterministic_run_on_good_lesson_goes_to_manual_review(qc_input):
    run = run_deterministic_qc(qc_input, now=NOW)
    assert run.qc1.issues == [] and run.qc2.issues == []
    # No problems found, but most categories were not checked yet: not ELIGIBLE.
    assert run.release.decision is ReleaseDecision.MANUAL_REVIEW
    assert run.qc1.score is None and run.qc2.score is None
    assert Evaluator.CITATION_CHECK in run.qc1.evaluators
    assert Evaluator.INSTRUCTIONAL_REVIEW not in run.qc2.evaluators
    time = next(s for s in run.qc2.subscores if s.name == "time_feasibility")
    assert time.score == 100


def test_deterministic_run_blocks_fabricated_citation(lesson_data, research_data):
    lesson_data["claims"][3]["source_ids"] = ["SRC-999"]
    run = run_deterministic_qc(build_qc_input(lesson_data, research_data), now=NOW)
    assert run.release.decision is ReleaseDecision.BLOCKED
    assert run.release.blocking_issue_ids == ["QC1-001"]


def test_deterministic_run_blocks_sixty_minute_lesson(lesson_data, research_data):
    lesson_data["sections"][2]["duration_minutes"] = 27
    lesson_data["stated_duration_minutes"] = 60
    run = run_deterministic_qc(build_qc_input(lesson_data, research_data), now=NOW)
    assert run.release.decision is ReleaseDecision.BLOCKED
    assert run.qc2.status is AuditStatus.BLOCKED
    assert run.qc1.status is AuditStatus.MANUAL_REVIEW  # QC1 judged independently


def test_deterministic_run_is_repeatable(qc_input):
    a = run_deterministic_qc(qc_input, now=NOW)
    b = run_deterministic_qc(qc_input, now=NOW)
    assert a == b
    assert a.qc1.model_dump_json() == b.qc1.model_dump_json()


def test_audit_report_is_json_serializable(qc_input):
    run = run_deterministic_qc(qc_input, now=NOW)
    restored = AuditReport.model_validate_json(run.qc2.model_dump_json())
    assert restored == run.qc2
