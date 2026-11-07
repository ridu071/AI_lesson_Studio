"""Grading the lesson test and deciding what to review.

Kept out of the UI so the rules are testable:
- each question type has one way of being right (case and spacing ignored);
- an objective scored below REVIEW_THRESHOLD opens its remedial block;
- the recap opens with a line built from the learner's results.
"""

from dataclasses import dataclass
from typing import Any

from app.schemas.enums import AssessmentKind, QuestionType
from app.schemas.lesson import AssessmentQuestion, LessonVersion

REVIEW_THRESHOLD = 0.70
CHOICE_TYPES = {QuestionType.MULTIPLE_CHOICE, QuestionType.SCENARIO, QuestionType.TRUE_FALSE}
PAIR_TYPES = {QuestionType.MATCH_PAIRS, QuestionType.LABEL_VISUAL}
GRADED_TYPES = CHOICE_TYPES | PAIR_TYPES | {QuestionType.ORDER_STEPS, QuestionType.FILL_BLANK}


def norm(text: Any) -> str:
    return " ".join(str(text or "").split()).casefold()


def final_questions(lesson: LessonVersion) -> list[AssessmentQuestion]:
    return [q for q in lesson.assessments if q.kind is AssessmentKind.FINAL]


def is_correct(q: AssessmentQuestion, answer: Any) -> bool:
    kind = q.question_type
    if answer is None:
        return False
    if kind in CHOICE_TYPES:
        return norm(answer) == norm(q.answer_key)
    if kind is QuestionType.ORDER_STEPS:
        return [norm(a) for a in answer] == [norm(s) for s in q.correct_order]
    if kind in PAIR_TYPES:
        return all(norm((answer or {}).get(left)) == norm(right) for left, right in q.pairs) and bool(q.pairs)
    if kind is QuestionType.FILL_BLANK:
        return norm(answer) in {norm(q.answer_key), *(norm(a) for a in q.accepted_answers)}
    return False  # ungraded types (short_answer) never count as wrong in practice: not used in tests


def chosen_misconception(q: AssessmentQuestion, answer: Any) -> str | None:
    """The misconception behind a wrong option the learner picked, if the lesson names one."""
    if q.question_type not in CHOICE_TYPES or answer is None:
        return None
    return next((w.misconception for w in q.wrong_options if norm(w.option) == norm(answer)), None)


@dataclass(frozen=True)
class ObjectiveScore:
    objective_id: str
    description: str
    correct: int
    total: int

    @property
    def ratio(self) -> float:
        return self.correct / self.total if self.total else 1.0

    @property
    def needs_review(self) -> bool:
        return self.total > 0 and self.ratio < REVIEW_THRESHOLD


def score_objectives(lesson: LessonVersion, answers: dict[str, Any]) -> list[ObjectiveScore]:
    questions = [q for q in final_questions(lesson) if q.question_type in GRADED_TYPES]
    scores = []
    for objective in lesson.learning_objectives:
        mine = [q for q in questions if objective.id in q.objective_ids]
        correct = sum(is_correct(q, answers.get(q.question_id)) for q in mine)
        scores.append(ObjectiveScore(objective.id, objective.description, correct, len(mine)))
    return scores


def personal_line(lesson: LessonVersion, answers: dict[str, Any]) -> str:
    questions = [q for q in final_questions(lesson) if q.question_type in GRADED_TYPES]
    right = sum(is_correct(q, answers.get(q.question_id)) for q in questions)
    scores = [s for s in score_objectives(lesson, answers) if s.total]
    opening = f"You scored {right} out of {len(questions)}."
    if not scores:
        return opening
    best = max(scores, key=lambda s: s.ratio)
    weak = [s for s in scores if s.needs_review]
    if not weak:
        return f"{opening} Strong across every objective - you're ready for the next steps below."
    weakest = min(weak, key=lambda s: s.ratio)
    return (f"{opening} Your strongest area: {best.description.rstrip('.')}. "
            f"Worth another look: {weakest.description.rstrip('.')}.")
