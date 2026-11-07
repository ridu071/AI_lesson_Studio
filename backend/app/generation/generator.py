"""Generates and revises lessons with the LLM.

The model writes the lesson body only. Code adds the lesson ID, version,
supplementary videos and (at render time) the reference list, so the model
can never invent a link. Each draft is checked before QC sees it: valid
structure, only evidence-bearing sources cited, 40-45 minutes. A draft that
fails is sent back once with the reasons.
"""

from typing import Any

from pydantic import Field

from app.llm.base import LLMClient, LLMInvalidOutputError, call_structured, to_prompt_json
from app.llm.prompts import load_prompt
from app.modules.qc.schemas import QCIssue
from app.schemas.common import ContractModel
from app.schemas.enums import AssessmentKind, ClaimType, LearnerLevel, SourceType
from app.schemas.lesson import (
    Activity,
    AssessmentQuestion,
    Claim,
    LearningObjective,
    LessonSection,
    LessonVersion,
    LessonVideo,
)
from app.schemas.research import ResearchPackage

MIN_MINUTES, MAX_MINUTES = 40, 45
MIN_EVIDENCE_CLAIMS = 5
EVIDENCE_CLAIMS = {ClaimType.FACTUAL, ClaimType.DEFINITION}


class GeneratedLesson(ContractModel):
    title: str
    learner_level: LearnerLevel = LearnerLevel.BEGINNER
    stated_duration_minutes: int = Field(ge=1, le=240)
    learning_objectives: list[LearningObjective]
    sections: list[LessonSection]
    claims: list[Claim] = []
    activities: list[Activity] = []
    assessments: list[AssessmentQuestion] = []


def _inline(schema: dict) -> dict:
    """Pydantic JSON schema -> self-contained schema (no $ref, no titles/defaults/patterns)."""
    defs = schema.get("$defs", {})

    metadata = ("title", "default", "$defs", "pattern", "additionalProperties")

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(defs[node["$ref"].split("/")[-1]])
            out = {}
            for key, value in node.items():
                if key == "properties":  # field names: keep all, including "title"
                    out[key] = {name: walk(sub) for name, sub in value.items()}
                elif key not in metadata:
                    out[key] = walk(value)
            return out
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


LESSON_SCHEMA = _inline(GeneratedLesson.model_json_schema())


def evidence_request(research: ResearchPackage) -> list[dict]:
    return [
        {"source_id": s.source_id, "source_title": s.title, "passage_id": p.passage_id, "text": p.text}
        for s in research.sources for p in s.evidence_passages
    ]


def supplementary_videos(research: ResearchPackage, video_minutes: dict[str, int]) -> list[LessonVideo]:
    videos = [s for s in research.sources if s.source_type is SourceType.VIDEO and s.url]
    return [
        LessonVideo(video_id=f"VID-{n:02d}", title=s.title, url=s.url, source_id=s.source_id,
                    duration_minutes=video_minutes.get(s.source_id, 0), is_mandatory=False)
        for n, s in enumerate(videos, start=1)
    ]


def _validator(lesson_id: str, version: int, research: ResearchPackage, videos: list[LessonVideo]):
    evidence_sources = {s.source_id for s in research.sources if s.evidence_passages}

    def validate(draft: GeneratedLesson) -> None:
        try:
            lesson = LessonVersion(lesson_id=lesson_id, version=version, videos=videos,
                                   **draft.model_dump())
        except ValueError as exc:
            raise LLMInvalidOutputError(str(exc)[:1200]) from exc
        problems = []
        total = sum(s.duration_minutes for s in lesson.sections)
        if not MIN_MINUTES <= total <= MAX_MINUTES:
            problems.append(f"section minutes add up to {total}; they must total {MIN_MINUTES}-{MAX_MINUTES}")
        if lesson.stated_duration_minutes != total:
            problems.append(f"stated_duration_minutes must equal the section total {total}")
        cited = {sid for s in lesson.sections for sid in s.source_ids}
        cited |= {sid for c in lesson.claims for sid in c.source_ids}
        bad = sorted(cited - evidence_sources)
        if bad:
            problems.append(f"only sources with evidence passages may be cited; remove {bad}")
        uncited = [c.claim_id for c in lesson.claims if c.claim_type in EVIDENCE_CLAIMS and not c.source_ids]
        if uncited:
            problems.append(f"factual/definition claims must cite a source: {uncited}")
        kinds = [q.kind for q in lesson.assessments]
        if kinds.count(AssessmentKind.KNOWLEDGE_CHECK) < 2 or kinds.count(AssessmentKind.FINAL) < 2:
            problems.append("include at least 2 knowledge_check and 2 final questions")
        if sum(c.claim_type in EVIDENCE_CLAIMS for c in lesson.claims) < MIN_EVIDENCE_CLAIMS:
            problems.append(f"record at least {MIN_EVIDENCE_CLAIMS} factual/definition claims; "
                            "the lesson must explain every part of the objective")
        if problems:
            raise LLMInvalidOutputError("; ".join(problems))

    return validate


def _to_lesson(draft: GeneratedLesson, lesson_id: str, version: int, videos: list[LessonVideo]) -> LessonVersion:
    return LessonVersion(lesson_id=lesson_id, version=version, videos=videos, **draft.model_dump())


def generate_lesson(
    *, title: str, objective: str, research: ResearchPackage, video_minutes: dict[str, int],
    client: LLMClient, lesson_id: str, learner_level: LearnerLevel = LearnerLevel.BEGINNER,
) -> tuple[LessonVersion, str]:
    prompt = load_prompt("generation/lesson.md")
    videos = supplementary_videos(research, video_minutes)
    request = {
        "lesson_title": title, "learning_objective": objective, "learner_level": learner_level,
        "evidence_passages": evidence_request(research),
    }
    draft = call_structured(
        client, system=prompt.text, user="INPUT:\n" + to_prompt_json(request),
        schema=LESSON_SCHEMA, output_model=GeneratedLesson,
        validate=_validator(lesson_id, 1, research, videos),
    )
    return _to_lesson(draft, lesson_id, 1, videos), prompt.version


def revise_lesson(
    *, lesson: LessonVersion, objective: str, research: ResearchPackage, issues: list[QCIssue],
    instructor_note: str, client: LLMClient,
) -> tuple[LessonVersion, str]:
    """Apply selected QC recommendations; returns the NEXT version (never edits in place)."""
    prompt = load_prompt("generation/revise.md")
    request = {
        "learning_objective": objective,
        "issues_to_fix": [
            {"issue_id": i.issue_id, "issue_type": i.issue_type, "where": [i.section_id, i.claim_id, i.objective_id],
             "problem": i.explanation, "recommendation": i.recommendation.action if i.recommendation else None}
            for i in issues
        ],
        "instructor_note": instructor_note or None,
        "current_lesson": lesson.model_dump(mode="json", exclude={"lesson_id", "version", "videos"}),
        "evidence_passages": evidence_request(research),
    }
    next_version = lesson.version + 1
    draft = call_structured(
        client, system=prompt.text, user="INPUT:\n" + to_prompt_json(request),
        schema=LESSON_SCHEMA, output_model=GeneratedLesson,
        validate=_validator(lesson.lesson_id, next_version, research, list(lesson.videos)),
    )
    return _to_lesson(draft, lesson.lesson_id, next_version, list(lesson.videos)), prompt.version
