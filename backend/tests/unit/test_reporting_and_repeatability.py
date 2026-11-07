from datetime import UTC, datetime

import pytest

from app.evaluation.benchmark import BenchmarkCase
from app.evaluation.repeatability import measure, signature
from app.llm.base import LLMUnavailableError
from app.modules.qc.engine import run_deterministic_qc, run_full_qc
from app.modules.qc.reporting import render_markdown
from tests.fakes import FakeLLM, clean_qc1
from tests.helpers import build_qc_input

NOW = datetime(2026, 11, 7, tzinfo=UTC)


# --- instructor report ---


def test_report_for_blocked_lesson_names_the_blocker(lesson_data, research_data):
    lesson_data["claims"][3]["source_ids"] = ["SRC-999"]
    qc_input = build_qc_input(lesson_data, research_data)
    text = render_markdown(qc_input, run_full_qc(qc_input, FakeLLM(), now=NOW))
    assert "## Decision: BLOCKED" in text
    assert "QC1-001 [CRITICAL] fabricated_citation** - **BLOCKS RELEASE**" in text
    assert "SRC-999" in text
    assert "Instructor only" in text


def test_report_quotes_the_evidence_passage(lesson_data, research_data):
    def contradicts(request):
        out = clean_qc1(request)
        out["claims"][1]["relations"] = [
            {"passage_id": "EV-002", "relation": "contradicts", "reason": "It says the opposite."}]
        return out
    qc_input = build_qc_input(lesson_data, research_data)
    text = render_markdown(qc_input, run_full_qc(qc_input, FakeLLM(qc1=contradicts), now=NOW))
    assert "Evidence EV-002 from SRC-001" in text
    assert "each input is paired with the desired output" in text  # the passage itself


def test_report_marks_uncited_evidence(lesson_data, research_data):
    def wrong_source(request):
        out = clean_qc1(request)
        out["claims"][3]["relations"] = [
            {"passage_id": "EV-001", "relation": "supports", "reason": "Says so."}]
        return out
    qc_input = build_qc_input(lesson_data, research_data)
    text = render_markdown(qc_input, run_full_qc(qc_input, FakeLLM(qc1=wrong_source), now=NOW))
    assert "| CL-004 | supported | EV-001 (SRC-001, not cited by the claim) |" in text
    assert "| CL-001 | supported | EV-001 (SRC-001) |" in text


def test_report_explains_unevaluated_categories(lesson_data, research_data):
    qc_input = build_qc_input(lesson_data, research_data)
    text = render_markdown(qc_input, run_deterministic_qc(qc_input, now=NOW))
    assert "## Decision: MANUAL REVIEW" in text
    assert "| clarity | 15% | not evaluated (needs instructional_review) |" in text
    assert "model none (deterministic checks only)" in text


def test_report_for_errored_audit_has_no_decision(lesson_data, research_data):
    qc_input = build_qc_input(lesson_data, research_data)
    run = run_full_qc(qc_input, FakeLLM(qc1=LLMUnavailableError("timed out")), now=NOW)
    text = render_markdown(qc_input, run)
    assert "## Decision: NONE YET" in text
    assert "could not finish" in text and "Rerun it" in text


# --- repeatability ---


CASE = BenchmarkCase.model_validate({
    "case_id": "T-001", "title": "Repeat", "rationale": "Test.", "base": "ml_intro",
    "expected": {"decision": "eligible_for_instructor_review"},
})


def flaky_qc2():
    """Reports a weak example on every other call."""
    calls = {"n": 0}
    def answer(request):
        calls["n"] += 1
        if calls["n"] % 2:
            return {"issues": []}
        return {"issues": [{"issue_type": "weak_example", "section_id": "SEC-04", "question_id": None,
                            "objective_id": None, "explanation": "The example is weak.",
                            "suggested_fix": "Improve it."}]}
    return answer


def runner_for(llm):
    return lambda qi: run_full_qc(qi, llm, now=NOW)


def test_stable_model_is_fully_repeatable():
    summary = measure([CASE], runner_for(FakeLLM()), runs=3)
    m = summary.metrics()
    assert m["decision_stability"] == 1.0 and m["issue_set_stability"] == 1.0
    assert m["flaky_issue_count"] == 0


def test_flaky_issue_is_detected():
    summary = measure([CASE], runner_for(FakeLLM(qc2=flaky_qc2())), runs=4)
    [case] = summary.cases
    assert case.flaky_issues == [(("qc2", "weak_example", "SEC-04"), 2)]
    assert not case.issues_stable
    assert case.decision_stable  # a low-severity flake does not change the decision
    assert "flaky: qc2/weak_example/SEC-04 (in 2 of 4 runs)" in summary.format_report()


def test_errored_runs_are_counted_not_compared():
    llm = FakeLLM(qc1=[LLMUnavailableError("down"), clean_qc1])
    [case] = measure([CASE], runner_for(llm), runs=3).cases
    assert case.errors == 1 and case.successful == 2 and case.decision_stable


def test_signature_ignores_issue_numbering(lesson_data, research_data):
    lesson_data["claims"][3]["source_ids"] = ["SRC-999"]
    run = run_deterministic_qc(build_qc_input(lesson_data, research_data), now=NOW)
    assert signature(run.qc1.issues[0]) == ("qc1", "fabricated_citation", "CL-004")


def test_needs_at_least_two_runs():
    with pytest.raises(ValueError):
        measure([CASE], runner_for(FakeLLM()), runs=1)


def test_error_messages_are_kept():
    llm = FakeLLM(qc1=[LLMUnavailableError("model timed out"), clean_qc1])
    [case] = measure([CASE], runner_for(llm), runs=2).cases
    assert case.error_messages == ("model timed out",)
