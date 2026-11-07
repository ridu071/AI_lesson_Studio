"""Assessment checks: Bloom alignment and answer-key validity.

Bloom alignment uses the levels declared in the lesson. Whether a question
really works at its declared level is judged by the LLM evaluator in Step 6.
"""

from app.modules.qc.enums import IssueType
from app.modules.qc.issues import IssueCollector
from app.schemas.enums import AssessmentKind, QuestionType, bloom_rank
from app.schemas.lesson import LessonVersion

_TRUE_FALSE = {"true", "false"}


def _norm(text: str) -> str:
    """Compare answers ignoring case and extra spaces."""
    return " ".join(text.split()).casefold()


def check_bloom_alignment(lesson: LessonVersion, issues: IssueCollector) -> None:
    for objective in lesson.learning_objectives:
        finals = [
            q
            for q in lesson.assessments
            if q.kind is AssessmentKind.FINAL and objective.id in q.objective_ids
        ]
        if not finals:
            continue  # reported as objective_not_assessed by the coverage check
        highest = max(finals, key=lambda q: bloom_rank(q.bloom_level))
        if bloom_rank(highest.bloom_level) < bloom_rank(objective.bloom_level):
            ids = ", ".join(q.question_id for q in finals)
            issues.add(
                IssueType.BLOOM_MISMATCH,
                f"Objective {objective.id} expects the '{objective.bloom_level}' level, but its "
                f"final assessment ({ids}) only reaches '{highest.bloom_level}'.",
                objective_id=objective.id,
                recommendation=f"Add a final question that requires the student to "
                f"{objective.bloom_level}, not just recall facts.",
            )


def check_answer_keys(lesson: LessonVersion, issues: IssueCollector) -> None:
    for q in lesson.assessments:
        options = [_norm(o) for o in q.options]
        answer = _norm(q.answer_key)

        if q.question_type is QuestionType.MULTIPLE_CHOICE:
            if len(options) < 2:
                issues.add(
                    IssueType.WEAK_ASSESSMENT,
                    f"{q.question_id} is multiple choice but has {len(options)} option(s).",
                    section_id=q.section_id,
                    recommendation="Give the question at least two plausible options.",
                )
            elif len(set(options)) != len(options):
                issues.add(
                    IssueType.WEAK_ASSESSMENT,
                    f"{q.question_id} has duplicate options.",
                    section_id=q.section_id,
                    recommendation="Make every option distinct.",
                )
            if answer not in options:
                issues.add(
                    IssueType.INCORRECT_ANSWER_KEY,
                    f"{q.question_id}: the answer key '{q.answer_key}' is not one of the options.",
                    section_id=q.section_id,
                    recommendation="Set the answer key to the correct option.",
                )

        elif q.question_type is QuestionType.ORDER_STEPS:
            steps = [_norm(s) for s in q.correct_order]
            if len(steps) < 3 or len(set(steps)) != len(steps):
                issues.add(
                    IssueType.WEAK_ASSESSMENT,
                    f"{q.question_id} asks to order steps but has fewer than 3 distinct steps.",
                    section_id=q.section_id,
                    recommendation="List at least 3 distinct steps in their correct order.",
                )

        elif q.question_type in (QuestionType.MATCH_PAIRS, QuestionType.LABEL_VISUAL):
            pairs = [p for p in q.pairs if len(p) == 2 and p[0].strip() and p[1].strip()]
            lefts, rights = [_norm(p[0]) for p in pairs], [_norm(p[1]) for p in pairs]
            if len(pairs) < 3 or len(set(lefts)) != len(lefts) or len(set(rights)) != len(rights):
                issues.add(
                    IssueType.WEAK_ASSESSMENT,
                    f"{q.question_id} needs at least 3 pairs, each item used once.",
                    section_id=q.section_id,
                    recommendation="Give 3+ pairs with no repeated items, so only one matching is correct.",
                )
            if q.question_type is QuestionType.LABEL_VISUAL and q.visual is None:
                issues.add(
                    IssueType.WEAK_ASSESSMENT,
                    f"{q.question_id} asks to label a visual but has no visual.",
                    section_id=q.section_id,
                    recommendation="Attach the visual whose numbered parts are to be labelled.",
                )

        elif q.question_type is QuestionType.TRUE_FALSE:
            if set(options) != _TRUE_FALSE:
                issues.add(
                    IssueType.WEAK_ASSESSMENT,
                    f"{q.question_id} is true/false but its options are not exactly "
                    "'True' and 'False'.",
                    section_id=q.section_id,
                    recommendation="Use exactly the options 'True' and 'False'.",
                )
            if answer not in _TRUE_FALSE:
                issues.add(
                    IssueType.INCORRECT_ANSWER_KEY,
                    f"{q.question_id}: a true/false answer key must be 'True' or 'False', "
                    f"not '{q.answer_key}'.",
                    section_id=q.section_id,
                    recommendation="Set the answer key to 'True' or 'False'.",
                )
