"""Grading the lesson test and choosing what to review."""

from app.generation.grading import (
    chosen_misconception,
    is_correct,
    personal_line,
    score_objectives,
)
from app.schemas.lesson import AssessmentQuestion, LessonVersion


def q(**kw) -> AssessmentQuestion:
    base = {"question_id": "Q-01", "section_id": "SEC-01", "kind": "final", "prompt": "Prompt?",
            "answer_key": "A", "explanation": "Because.", "objective_ids": ["LO-01"], "bloom_level": "apply"}
    return AssessmentQuestion.model_validate(base | kw)


def test_choice_answers_ignore_case_and_spacing():
    question = q(question_type="multiple_choice", options=["Labelled data", "No data"], answer_key="Labelled data")
    assert is_correct(question, "  labelled   DATA ")
    assert not is_correct(question, "No data")
    assert not is_correct(question, None)


def test_order_steps_must_match_exactly():
    question = q(question_type="order_steps", correct_order=["Collect", "Label", "Train"], answer_key="x")
    assert is_correct(question, ["collect", "Label", "train"])
    assert not is_correct(question, ["Label", "Collect", "Train"])
    assert not is_correct(question, ["Collect", "Label"])


def test_pairs_need_every_match_right():
    question = q(question_type="match_pairs", pairs=[["GET", "Read"], ["POST", "Send"], ["404", "Not found"]],
                 answer_key="x")
    assert is_correct(question, {"GET": "Read", "POST": "Send", "404": "Not found"})
    assert not is_correct(question, {"GET": "Send", "POST": "Read", "404": "Not found"})


def test_fill_blank_accepts_listed_variants():
    question = q(question_type="fill_blank", answer_key="labels", accepted_answers=["labelled data"])
    assert is_correct(question, "Labels") and is_correct(question, "labelled data")
    assert not is_correct(question, "clusters")


def test_wrong_choice_reveals_its_misconception():
    question = q(question_type="multiple_choice", options=["A", "B"], answer_key="A",
                 wrong_options=[{"option": "B", "misconception_id": "M1", "misconception": "Mixes up A and B."}])
    assert chosen_misconception(question, "B") == "Mixes up A and B."
    assert chosen_misconception(question, "A") is None


def _lesson(lesson_data) -> LessonVersion:
    data = dict(lesson_data)
    data["assessments"] = [
        q(question_id=f"Q-0{i}", section_id="SEC-07", question_type="multiple_choice", options=["A", "B"],
          answer_key="A", objective_ids=["LO-01" if i <= 3 else "LO-02"]).model_dump(mode="json")
        for i in range(1, 7)
    ]
    return LessonVersion.model_validate(data)


def test_objective_below_70_percent_needs_review(lesson_data):
    lesson = _lesson(lesson_data)
    answers = {"Q-01": "A", "Q-02": "A", "Q-03": "A", "Q-04": "A", "Q-05": "B", "Q-06": "B"}
    scores = {s.objective_id: s for s in score_objectives(lesson, answers)}
    assert (scores["LO-01"].correct, scores["LO-01"].needs_review) == (3, False)
    assert (scores["LO-02"].correct, scores["LO-02"].needs_review) == (1, True)  # 33% < 70%
    line = personal_line(lesson, answers)
    assert line.startswith("You scored 4 out of 6.") and "Worth another look" in line


def test_all_strong_gives_encouraging_line(lesson_data):
    lesson = _lesson(lesson_data)
    line = personal_line(lesson, {f"Q-0{i}": "A" for i in range(1, 7)})
    assert line.startswith("You scored 6 out of 6.") and "Strong across every objective" in line
