"""QC2 LLM review: the judgements code cannot make (clarity, example and
activity quality, answer correctness, real Bloom level).

The model may only report the issue types in LLM_ISSUE_TYPES, and only at
locations that exist in the lesson. Severity always comes from policy.py,
never from the model. An issue the deterministic checks already reported at
the same place is not reported twice.
"""

from pydantic import model_validator

from app.llm.base import LLMClient, LLMInvalidOutputError, call_structured, to_prompt_json
from app.llm.prompts import load_prompt
from app.modules.qc.enums import IssueType
from app.modules.qc.issues import IssueCollector
from app.modules.qc.schemas import QCInput
from app.schemas.common import ContractModel, NonEmptyStr

PROMPT_PATH = "qc2/llm_review.md"

LLM_ISSUE_TYPES = (
    IssueType.UNCLEAR_EXPLANATION,
    IssueType.WEAK_EXAMPLE,
    IssueType.UNCLEAR_ACTIVITY,
    IssueType.WEAK_ASSESSMENT,
    IssueType.INCORRECT_ANSWER_KEY,
    IssueType.BLOOM_MISMATCH,
    IssueType.POOR_SEQUENCING,
    IssueType.OBJECTIVE_NOT_EXPLAINED,
    IssueType.ACCESSIBILITY_ISSUE,
)


class ReviewIssue(ContractModel):
    issue_type: IssueType
    section_id: str | None = None
    question_id: str | None = None
    objective_id: str | None = None
    explanation: NonEmptyStr
    suggested_fix: NonEmptyStr

    @model_validator(mode="after")
    def _allowed_type(self) -> "ReviewIssue":
        if self.issue_type not in LLM_ISSUE_TYPES:
            raise ValueError(f"issue type '{self.issue_type}' is not allowed here")
        return self


class QC2Review(ContractModel):
    issues: list[ReviewIssue]


_NULLABLE_TEXT = {"type": ["string", "null"]}
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "issue_type": {"type": "string", "enum": [t.value for t in LLM_ISSUE_TYPES]},
                    "section_id": _NULLABLE_TEXT,
                    "question_id": _NULLABLE_TEXT,
                    "objective_id": _NULLABLE_TEXT,
                    "explanation": {"type": "string"},
                    "suggested_fix": {"type": "string"},
                },
                "required": [
                    "issue_type", "section_id", "question_id", "objective_id",
                    "explanation", "suggested_fix",
                ],
            },
        }
    },
    "required": ["issues"],
}


def build_request(qc_input: QCInput) -> dict:
    lesson = qc_input.lesson
    return {
        "request_objective": qc_input.request_objective,
        "lesson_title": lesson.title,
        "learner_level": lesson.learner_level,
        "learning_objectives": [
            {"objective_id": o.id, "description": o.description, "bloom_level": o.bloom_level}
            for o in lesson.learning_objectives
        ],
        "sections": [
            s.model_dump(mode="json", exclude={"source_ids"}) for s in lesson.sections
        ],
        "activities": [a.model_dump(mode="json") for a in lesson.activities],
        "assessments": [q.model_dump(mode="json") for q in lesson.assessments],
    }


def make_validator(qc_input: QCInput):
    lesson = qc_input.lesson
    sections = {s.section_id for s in lesson.sections}
    questions = {q.question_id for q in lesson.assessments}
    objectives = {o.id for o in lesson.learning_objectives}

    def validate(review: QC2Review) -> None:
        problems = []
        for i in review.issues:
            if i.section_id is not None and i.section_id not in sections:
                problems.append(f"unknown section {i.section_id}")
            if i.question_id is not None and i.question_id not in questions:
                problems.append(f"unknown question {i.question_id}")
            if i.objective_id is not None and i.objective_id not in objectives:
                problems.append(f"unknown objective {i.objective_id}")
        if problems:
            raise LLMInvalidOutputError("; ".join(problems))

    return validate


def _already_reported(issues: IssueCollector, issue_type, section_id, objective_id) -> bool:
    return any(
        e.issue_type is issue_type
        and (objective_id is None or e.objective_id is None or e.objective_id == objective_id)
        and (section_id is None or e.section_id is None or e.section_id == section_id)
        for e in issues.issues
    )


def run_qc2_llm_review(qc_input: QCInput, issues: IssueCollector, client: LLMClient) -> str:
    """Adds the model's findings to `issues`. Returns the prompt version used."""
    prompt = load_prompt(PROMPT_PATH)
    review = call_structured(
        client,
        system=prompt.text,
        user="INPUT:\n" + to_prompt_json(build_request(qc_input)),
        schema=RESPONSE_SCHEMA,
        output_model=QC2Review,
        validate=make_validator(qc_input),
    )
    section_of_question = {q.question_id: q.section_id for q in qc_input.lesson.assessments}

    for found in review.issues:
        # A question's own section is authoritative.
        section_id = section_of_question.get(found.question_id, found.section_id)
        if _already_reported(issues, found.issue_type, section_id, found.objective_id):
            continue
        where = f"{found.question_id}: " if found.question_id else ""
        explanation = f"{where}{found.explanation}"
        if len(explanation) < 10:
            explanation = f"{found.issue_type}: {explanation}"
        issues.add(
            found.issue_type,
            explanation,
            section_id=section_id,
            objective_id=found.objective_id,
            recommendation=found.suggested_fix,
        )
    return prompt.version
