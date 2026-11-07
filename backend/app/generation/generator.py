"""Generates and revises lessons with the LLM.

The model writes the lesson body only. Code adds the lesson ID, version,
supplementary videos and (at render time) the reference list, so the model
can never invent a link. Each draft is checked before QC sees it: valid
structure, only evidence-bearing sources cited, 40-45 minutes. A draft that
fails is sent back once with the reasons.
"""

from typing import Any

from pydantic import Field, model_validator

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
# A whole lesson is a large answer; allow two corrections before giving up.
GENERATION_ATTEMPTS = 3
EVIDENCE_CLAIMS = {ClaimType.FACTUAL, ClaimType.DEFINITION}


_ID_PREFIX = {"learning_objectives": ("id", "LO"), "sections": ("section_id", "SEC"),
              "claims": ("claim_id", "CL"), "activities": ("activity_id", "ACT"),
              "assessments": ("question_id", "Q")}


def normalize_ids(raw: Any) -> Any:
    """Renumber the model's IDs into the standard format (LO-01, SEC-01, CL-01, ...)
    and rewrite every reference to them, so a naming slip like 'CLM-01' can
    never fail a lesson. Unknown references are left alone for validation to catch."""
    if not isinstance(raw, dict):
        return raw
    data = {k: v for k, v in raw.items()}
    maps: dict[str, dict[str, str]] = {}
    for field, (key, prefix) in _ID_PREFIX.items():
        items = [dict(item) for item in data.get(field) or [] if isinstance(item, dict)]
        maps[prefix] = {}
        for n, item in enumerate(items, start=1):
            new_id = f"{prefix}-{n:02d}"
            if item.get(key) is not None:
                maps[prefix].setdefault(str(item[key]), new_id)
            item[key] = new_id
        if field in data:
            data[field] = items

    def remap(prefix: str, value: Any) -> Any:
        return maps[prefix].get(str(value), value) if value is not None else value

    for section in data.get("sections", []):
        section["objective_ids"] = [remap("LO", o) for o in section.get("objective_ids") or []]
    for claim in data.get("claims", []):
        claim["section_id"] = remap("SEC", claim.get("section_id"))
    for item in data.get("activities", []) + data.get("assessments", []):
        item["section_id"] = remap("SEC", item.get("section_id"))
        item["objective_ids"] = [remap("LO", o) for o in item.get("objective_ids") or []]
    return data


class GeneratedLesson(ContractModel):
    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, raw: Any) -> Any:
        return normalize_ids(raw)

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
        checks, finals = kinds.count(AssessmentKind.KNOWLEDGE_CHECK), kinds.count(AssessmentKind.FINAL)
        if checks < 2 or finals < 2:
            problems.append(f"you wrote {checks} knowledge_check and {finals} final questions; write at "
                            "least 2 of each (put knowledge_check questions in the knowledge_check section "
                            "and final questions in the final_assessment section)")
        facts = sum(c.claim_type in EVIDENCE_CLAIMS for c in lesson.claims)
        if facts < MIN_EVIDENCE_CLAIMS:
            problems.append(f"you recorded {facts} factual/definition claims; record at least "
                            f"{MIN_EVIDENCE_CLAIMS} - every definition and fact you state in the content "
                            "must appear in 'claims' with its source_ids")
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
        attempts=GENERATION_ATTEMPTS,
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
        attempts=GENERATION_ATTEMPTS,
    )
    return _to_lesson(draft, lesson.lesson_id, next_version, list(lesson.videos)), prompt.version
