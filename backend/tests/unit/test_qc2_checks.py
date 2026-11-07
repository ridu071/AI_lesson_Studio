from app.modules.qc.enums import IssueType, Severity
from app.modules.qc.qc2.deterministic import run_qc2_checks
from tests.helpers import build_qc_input

T = IssueType


def run(lesson, research, **kwargs):
    return run_qc2_checks(build_qc_input(lesson, research), max_minutes=45, **kwargs)


def types(result):
    return [i.issue_type for i in result.issues]


def test_valid_lesson_has_no_instructional_issues(lesson_data, research_data):
    result = run(lesson_data, research_data)
    assert result.issues == []
    assert result.mandatory_minutes == 45
    assert all(row.is_complete for row in result.coverage)


# --- duration (E2E-007) ---


def test_sixty_minute_lesson_is_blocked(lesson_data, research_data):
    lesson_data["sections"][2]["duration_minutes"] = 27  # 45 -> 60
    lesson_data["stated_duration_minutes"] = 60
    result = run(lesson_data, research_data)
    [issue] = result.issues
    assert issue.issue_type is T.DURATION_EXCEEDED
    assert issue.hard_gate and issue.blocks_release
    assert "60 minutes" in issue.explanation
    assert result.mandatory_minutes == 60


def test_understated_duration_is_also_a_mismatch(lesson_data, research_data):
    # The generator claims 45 but the sections add up to 60.
    lesson_data["sections"][2]["duration_minutes"] = 27
    assert types(run(lesson_data, research_data)) == [T.DURATION_EXCEEDED, T.DURATION_MISMATCH]


def test_mandatory_video_counts_but_optional_does_not(lesson_data, research_data):
    assert run(lesson_data, research_data).mandatory_minutes == 45  # 10-min video is optional
    lesson_data["videos"][0]["is_mandatory"] = True
    result = run(lesson_data, research_data)
    assert result.mandatory_minutes == 55
    assert T.DURATION_EXCEEDED in types(result)


def test_activity_longer_than_its_section_is_flagged(lesson_data, research_data):
    lesson_data["activities"][0]["duration_minutes"] = 15  # SEC-05 allows 8
    [issue] = run(lesson_data, research_data).issues
    assert issue.issue_type is T.DURATION_MISMATCH
    assert issue.section_id == "SEC-05"


def test_limit_comes_from_settings_when_not_given(lesson_data, research_data):
    result = run_qc2_checks(build_qc_input(lesson_data, research_data))
    assert result.issues == []  # default MAX_LESSON_MINUTES is 45


# --- coverage matrix (E2E-006) ---


def test_objective_missing_from_final_assessment_is_blocked(lesson_data, research_data):
    for q in lesson_data["assessments"]:
        if q["kind"] == "final":
            q["objective_ids"] = ["LO-01"]
    result = run(lesson_data, research_data)
    [issue] = result.issues
    assert issue.issue_type is T.OBJECTIVE_NOT_ASSESSED
    assert issue.objective_id == "LO-02"
    assert issue.hard_gate
    lo2 = next(r for r in result.coverage if r.objective_id == "LO-02")
    assert not lo2.assessed and not lo2.is_complete


def test_knowledge_check_alone_does_not_count_as_assessed(lesson_data, research_data):
    # Q-02 (knowledge check) still tests LO-02, but no final question does.
    for q in lesson_data["assessments"]:
        if q["kind"] == "final":
            q["objective_ids"] = ["LO-01"]
    assert T.OBJECTIVE_NOT_ASSESSED in types(run(lesson_data, research_data))


def _lo2_only_tested_at_understand_level(lesson_data):
    """LO-02 keeps an assessment but loses its activity and its applied questions."""
    lesson_data["activities"][0]["objective_ids"] = ["LO-01"]
    for q in lesson_data["assessments"]:
        if q["kind"] == "final":
            q["objective_ids"] = ["LO-01"]
    lesson_data["assessments"].append({
        "question_id": "Q-05", "section_id": "SEC-07", "kind": "final", "question_type": "multiple_choice",
        "prompt": "Which task groups data without labels?", "options": ["Clustering", "Classification"],
        "answer_key": "Clustering", "explanation": "Clustering needs no labels.",
        "objective_ids": ["LO-02"], "bloom_level": "understand"})


def test_objective_without_practice_is_flagged(lesson_data, research_data):
    _lo2_only_tested_at_understand_level(lesson_data)
    [issue] = run(lesson_data, research_data).issues
    assert issue.issue_type is T.OBJECTIVE_NOT_PRACTICED
    assert issue.objective_id == "LO-02"
    assert issue.severity is Severity.MEDIUM


def test_applied_question_counts_as_practice(lesson_data, research_data):
    # No activity at all, but both objectives have analyze-level questions: practised.
    lesson_data["activities"][0]["is_mandatory"] = False
    result = run(lesson_data, research_data)
    assert result.issues == []
    assert all(row.practiced for row in result.coverage)


def test_objective_never_explained_is_flagged(lesson_data, research_data):
    lesson_data["sections"][2]["objective_ids"] = ["LO-01"]
    [issue] = run(lesson_data, research_data).issues
    assert issue.issue_type is T.OBJECTIVE_NOT_EXPLAINED
    assert issue.objective_id == "LO-02"


# --- Bloom alignment ---


def test_recall_questions_for_an_analyze_objective_are_flagged(lesson_data, research_data):
    # "Differentiate" (analyze) tested only by "What is...?" (remember).
    for q in lesson_data["assessments"]:
        if q["kind"] == "final":
            q["bloom_level"] = "remember"
    issues = run(lesson_data, research_data).issues
    assert [(i.issue_type, i.objective_id) for i in issues] == [
        (T.BLOOM_MISMATCH, "LO-01"),
        (T.BLOOM_MISMATCH, "LO-02"),
    ]


def test_assessment_above_objective_level_is_fine(lesson_data, research_data):
    # LO-02 is "understand"; its final questions are "analyze". Harder is acceptable.
    assert run(lesson_data, research_data).issues == []


# --- answer keys ---


def test_answer_key_not_among_options(lesson_data, research_data):
    lesson_data["assessments"][0]["answer_key"] = "Labeled data only"
    [issue] = run(lesson_data, research_data).issues
    assert issue.issue_type is T.INCORRECT_ANSWER_KEY
    assert "Q-01" in issue.explanation


def test_answer_key_comparison_ignores_case_and_spaces(lesson_data, research_data):
    lesson_data["assessments"][0]["answer_key"] = "  labelled   DATA "
    assert run(lesson_data, research_data).issues == []


def test_multiple_choice_with_one_option(lesson_data, research_data):
    lesson_data["assessments"][0]["options"] = ["Labelled data"]
    assert types(run(lesson_data, research_data)) == [T.WEAK_ASSESSMENT]


def test_multiple_choice_with_duplicate_options(lesson_data, research_data):
    lesson_data["assessments"][0]["options"] = ["Labelled data", "labelled data", "No data"]
    assert types(run(lesson_data, research_data)) == [T.WEAK_ASSESSMENT]


def test_true_false_with_invalid_answer(lesson_data, research_data):
    lesson_data["assessments"][1]["answer_key"] = "Yes"
    assert types(run(lesson_data, research_data)) == [T.INCORRECT_ANSWER_KEY]


# --- structure and ordering ---


def test_missing_summary_is_flagged(lesson_data, research_data):
    lesson_data["sections"] = [s for s in lesson_data["sections"] if s["section_type"] != "summary"]
    lesson_data["stated_duration_minutes"] = 42
    [issue] = run(lesson_data, research_data).issues
    assert issue.issue_type is T.MISSING_SECTION
    assert "summary" in issue.explanation


def test_introduction_not_first_is_flagged(lesson_data, research_data):
    s = lesson_data["sections"]
    s[0], s[1] = s[1], s[0]
    [issue] = run(lesson_data, research_data).issues
    assert issue.issue_type is T.POOR_SEQUENCING


def test_practice_before_explanation_is_flagged(lesson_data, research_data):
    s = lesson_data["sections"]
    activity = s.pop(4)  # SEC-05 practical_application
    s.insert(1, activity)  # now before the concept explanation (SEC-03)
    issues = run(lesson_data, research_data).issues
    assert {i.issue_type for i in issues} == {T.POOR_SEQUENCING}
    assert {i.objective_id for i in issues} == {"LO-01", "LO-02"}
    assert all(i.section_id == "SEC-05" for i in issues)


# --- QC1 and QC2 stay independent ---


def test_qc2_does_not_report_factual_problems(lesson_data, research_data):
    lesson_data["claims"][3]["source_ids"] = ["SRC-999"]  # QC1's job
    assert run(lesson_data, research_data).issues == []
