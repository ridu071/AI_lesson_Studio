from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.evaluation.benchmark import (
    BenchmarkCase,
    build_input,
    load_cases,
    run_benchmark,
    run_case,
)
from app.evaluation.patch import PatchError, apply_patch
from app.modules.qc.engine import DETERMINISTIC_EVALUATORS, run_deterministic_qc

SETTINGS = Settings(_env_file=None, max_lesson_minutes=45, qc1_min_score=80, qc2_min_score=80)
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def runner(qc_input):
    return run_deterministic_qc(qc_input, settings=SETTINGS, now=NOW)


def case(**overrides) -> BenchmarkCase:
    data = {
        "case_id": "T-001",
        "title": "Test case",
        "rationale": "For testing the runner.",
        "base": "ml_intro",
        "mutations": [],
        "expected": {"decision": "eligible_for_instructor_review", "issues": []},
    }
    return BenchmarkCase.model_validate(data | overrides)


# --- JSON patch ---


def test_patch_replace_add_remove():
    doc = {"a": [1, 2, 3], "b": {"c": 1}}
    out = apply_patch(doc, [
        {"op": "replace", "path": "/b/c", "value": 9},
        {"op": "add", "path": "/a/-", "value": 4},
        {"op": "add", "path": "/a/0", "value": 0},
        {"op": "remove", "path": "/a/1"},
    ])
    assert out == {"a": [0, 2, 3, 4], "b": {"c": 9}}
    assert doc == {"a": [1, 2, 3], "b": {"c": 1}}  # original untouched


@pytest.mark.parametrize("op", [
    {"op": "replace", "path": "/b/missing", "value": 1},
    {"op": "remove", "path": "/a/7"},
    {"op": "add", "path": "/a/9", "value": 1},
])
def test_patch_rejects_paths_that_do_not_exist(op):
    # A typo in a benchmark case must fail loudly, not silently test nothing.
    with pytest.raises(PatchError):
        apply_patch({"a": [1], "b": {}}, [op])


def test_mutation_needs_a_value():
    with pytest.raises(ValidationError, match="needs a value"):
        case(mutations=[{"op": "replace", "path": "/lesson/title"}])


def test_mutation_can_only_touch_qc_input():
    with pytest.raises(ValidationError):
        case(mutations=[{"op": "replace", "path": "/settings/max", "value": 99}])


# --- the dataset itself ---


def test_all_cases_load_and_build():
    cases = load_cases()
    assert len(cases) >= 25
    for c in cases:
        build_input(c)  # every mutation applies and gives a valid QCInput


def test_every_case_is_in_the_folder_matching_its_prefix():
    from app.evaluation.benchmark import EVALUATION_DIR

    folder_for = {"C": "control_cases", "F": "factual_test_cases", "I": "instructional_test_cases"}
    for folder in folder_for.values():
        for path in (EVALUATION_DIR / folder).glob("*.json"):
            c = BenchmarkCase.model_validate_json(path.read_text(encoding="utf-8"))
            assert folder_for[c.case_id[0]] == folder, path.name
            assert path.stem == c.case_id, path.name


def test_benchmark_passes_in_deterministic_mode():
    summary = run_benchmark(runner, DETERMINISTIC_EVALUATORS)
    assert summary.failures == [], summary.format_report()
    m = summary.metrics()
    assert m["false_blocks"] == 0 and m["missed_blocks"] == 0
    assert m["cases_skipped"] == 6


def test_only_llm_cases_are_skipped():
    summary = run_benchmark(runner, DETERMINISTIC_EVALUATORS)
    for r in summary.results:
        assert r.ran == (not r.case.requires_evaluators)


# --- the runner can fail ---


def test_runner_reports_a_missed_issue():
    # Expect an issue the lesson does not have.
    result = run_case(
        case(expected={"decision": "blocked", "issues": [{"issue_type": "fabricated_citation"}]}),
        runner, DETERMINISTIC_EVALUATORS,
    )
    assert not result.passed
    assert [e.issue_type for e in result.missed] == ["fabricated_citation"]


def test_runner_reports_a_false_alarm():
    # Break the lesson but expect nothing: the issue QC finds counts as unexpected.
    result = run_case(
        case(mutations=[{"op": "replace", "path": "/lesson/stated_duration_minutes", "value": 40}]),
        runner, DETERMINISTIC_EVALUATORS,
    )
    assert not result.passed
    assert [i.issue_type for i in result.unexpected] == ["duration_mismatch"]


def test_runner_checks_location():
    # Right issue type, wrong claim: does not count as found.
    result = run_case(
        case(
            mutations=[{"op": "replace", "path": "/lesson/claims/3/source_ids", "value": ["SRC-999"]}],
            expected={"decision": "blocked",
                      "issues": [{"issue_type": "fabricated_citation", "claim_id": "CL-001"}]},
        ),
        runner, DETERMINISTIC_EVALUATORS,
    )
    assert not result.passed and len(result.missed) == 1 and len(result.unexpected) == 1


def test_runner_reports_a_wrong_block_decision():
    result = run_case(
        case(
            mutations=[{"op": "replace", "path": "/lesson/claims/3/source_ids", "value": ["SRC-999"]}],
            expected={"decision": "eligible_for_instructor_review",
                      "issues": [{"issue_type": "fabricated_citation"}]},
        ),
        runner, DETERMINISTIC_EVALUATORS,
    )
    assert result.actual_block and not result.expected_block
    assert not result.passed


def test_skipped_case_never_counts_as_passed():
    result = run_case(case(requires_evaluators=["claim_verification"]), runner,
                      DETERMINISTIC_EVALUATORS)
    assert not result.ran and not result.passed
    assert result.skipped_reason == "needs claim_verification"


def test_acceptable_extra_issue_is_not_a_false_alarm():
    mutation = [{"op": "replace", "path": "/lesson/stated_duration_minutes", "value": 40}]
    strict = run_case(case(mutations=mutation), runner, DETERMINISTIC_EVALUATORS)
    lenient = run_case(
        case(mutations=mutation, expected={"decision": "eligible_for_instructor_review",
                                           "acceptable": [{"issue_type": "duration_mismatch"}]}),
        runner, DETERMINISTIC_EVALUATORS,
    )
    assert not strict.passed
    assert lenient.passed and lenient.unexpected == []


def test_errored_case_is_reported_but_not_scored():
    from app.llm.base import LLMUnavailableError
    from app.modules.qc.engine import FULL_EVALUATORS, run_full_qc
    from tests.fakes import FakeLLM

    broken = FakeLLM(qc1=LLMUnavailableError("timed out"))
    result = run_case(case(), lambda qi: run_full_qc(qi, broken, settings=SETTINGS, now=NOW),
                      FULL_EVALUATORS)
    assert result.ran and not result.scored and not result.passed
    assert "timed out" in result.error

    from app.evaluation.benchmark import BenchmarkSummary
    m = BenchmarkSummary([result]).metrics()
    assert m["cases_errored"] == 1 and m["false_negatives"] == 0


def test_issue_needing_an_evaluator_that_did_not_run_is_not_required():
    expected = {"decision": "eligible_for_instructor_review",
                "issues": [{"issue_type": "research_gap", "needs": "gap_detection"}]}
    result = run_case(case(expected=expected), runner, DETERMINISTIC_EVALUATORS)
    assert result.passed and result.missed == []
