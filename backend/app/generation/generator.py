"""Generates and revises lessons with the LLM.

The model writes the lesson body only. Code adds the lesson ID, version,
supplementary videos and (at render time) the reference list, so the model
can never invent a link. Each draft is checked before QC sees it: valid
structure, only evidence-bearing sources cited, 40-45 minutes. A draft that
fails is sent back once with the reasons.
"""

from typing import Any

from pydantic import Field, ValidationInfo, model_validator

from app.llm.base import LLMClient, LLMError, LLMInvalidOutputError, call_structured, to_prompt_json
from app.llm.prompts import load_prompt
from app.modules.qc.schemas import QCIssue
from app.schemas.common import ContractModel, NonEmptyStr
from app.schemas.enums import AssessmentKind, ClaimType, ContentBlockType, LearnerLevel, SectionType, SourceType
from app.schemas.lesson import (
    Activity,
    AssessmentQuestion,
    Claim,
    LearningObjective,
    LessonSection,
    LessonVersion,
    LessonVideo,
    Remedial,
)
from app.schemas.research import ResearchPackage

MIN_MINUTES, MAX_MINUTES = 40, 45
MIN_EVIDENCE_CLAIMS = 3  # maths/skills lessons state fewer facts; every stated fact must still be cited
# Check questions are requested but not required: a lesson is not failed for lacking them.
MIN_CHECKS = 0
TEST_QUESTIONS = 10  # every lesson's test has exactly this many questions, whatever the topic
# A whole lesson is a large answer; allow two corrections before giving up.
GENERATION_ATTEMPTS = 3
EVIDENCE_CLAIMS = {ClaimType.FACTUAL, ClaimType.DEFINITION}


_ID_PREFIX = {"learning_objectives": ("id", "LO"), "sections": ("section_id", "SEC"),
              "claims": ("claim_id", "CL"), "activities": ("activity_id", "ACT"),
              "assessments": ("question_id", "Q")}


CALLOUT_LABELS = ("Key idea", "Common mistake", "Tip")


def _repair_block(block: Any) -> Any:
    """Move text the model put in the wrong field into `content`, so a misplaced field
    (e.g. a callout's text in `label` or `caption`) never fails a whole lesson."""
    if not isinstance(block, dict) or block.get("type") in ("visual", "bullets"):
        return block
    block = dict(block)
    if (block.get("content") or "").strip():
        return block
    label = (block.get("label") or "").strip()
    if block.get("type") == "callout" and label and label not in CALLOUT_LABELS:
        known = next((k for k in CALLOUT_LABELS if label.lower().startswith(k.lower())), None)
        block["label"] = known or "Key idea"
        block["content"] = label[len(known):].lstrip(" :-") if known else label
    elif (block.get("caption") or "").strip():
        block["content"] = block["caption"]
    elif block.get("items"):
        block["content"] = " ".join(str(i) for i in block["items"])
    if not (block.get("content") or "").strip():
        return None  # an empty text block teaches nothing: drop it rather than fail the lesson
    return block


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
        repaired = (_repair_block(b) for b in section.get("content_blocks") or [])
        section["content_blocks"] = [b for b in repaired if b is not None]
    for claim in data.get("claims", []):
        claim["section_id"] = remap("SEC", claim.get("section_id"))
    for item in data.get("activities", []) + data.get("assessments", []):
        item["section_id"] = remap("SEC", item.get("section_id"))
        item["objective_ids"] = [remap("LO", o) for o in item.get("objective_ids") or []]
    return _keep_ten_test_questions(data)


def _drop_non_evidence_citations(data: dict, evidence: set[str]) -> None:
    """Remove citations of sources that have no evidence passages (books, videos, unknown IDs).
    A fact left with no real source is still caught by validation and sent back."""
    for item in data.get("claims", []) + data.get("sections", []):
        if isinstance(item, dict):
            item["source_ids"] = [s for s in item.get("source_ids") or [] if s in evidence]


def _fill_missing_hints(data: Any) -> Any:
    """A test question without a hint gets a safe nudge to the section it tests.
    It points to where the idea is taught and never reveals the answer."""
    if not isinstance(data, dict):
        return data
    titles = {s.get("section_id"): s.get("title") for s in data.get("sections", []) if isinstance(s, dict)}
    for q in data.get("assessments", []):
        if isinstance(q, dict) and q.get("kind") == "final" and not (q.get("hint") or "").strip():
            title = titles.get(q.get("review_section_id"))
            q["hint"] = (f'Think back to the section "{title}".' if title
                         else "Think back to the two core ideas before you answer.")
    return data


def _keep_ten_test_questions(data: dict) -> dict:
    """If the model wrote MORE than 10 test questions, keep the first 10 (they are ordered
    easy to hard). Fewer than 10 is not padded: the draft is sent back instead."""
    finals = [q for q in data.get("assessments", []) if isinstance(q, dict) and q.get("kind") == "final"]
    if len(finals) <= TEST_QUESTIONS:
        return data
    drop = {id(q) for q in finals[TEST_QUESTIONS:]}
    data["assessments"] = [q for q in data["assessments"] if id(q) not in drop]
    return data


class GeneratedLesson(ContractModel):
    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, raw: Any, info: ValidationInfo) -> Any:
        data = normalize_ids(raw)
        evidence = (info.context or {}).get("evidence_sources")
        if isinstance(data, dict) and evidence is not None:
            _drop_non_evidence_citations(data, evidence)
        return _fill_missing_hints(data)

    title: str
    learner_level: LearnerLevel = LearnerLevel.BEGINNER
    stated_duration_minutes: int = Field(ge=1, le=240)
    learning_objectives: list[LearningObjective]
    sections: list[LessonSection]
    claims: list[Claim] = []
    activities: list[Activity] = []
    assessments: list[AssessmentQuestion] = []
    remedials: list[Remedial] = []


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
        checks = [q for q in lesson.assessments if q.kind is AssessmentKind.KNOWLEDGE_CHECK]
        finals = [q for q in lesson.assessments if q.kind is AssessmentKind.FINAL]
        if len(checks) < MIN_CHECKS:
            problems.append(f"you wrote {len(checks)} check questions; write one knowledge_check "
                            "short_answer question in each core idea section")
        if len(finals) != TEST_QUESTIONS:
            problems.append(f"you wrote {len(finals)} test questions; the Test section needs exactly "
                            f"{TEST_QUESTIONS} final questions (understand, then apply, then transfer)")
        types = {q.question_type for q in finals}
        if finals and len(types) < 3:
            problems.append(f"the test uses {len(types)} question types; use at least 3 different types")
        no_hint = [q.question_id for q in finals if not (q.hint or "").strip()]
        if no_hint:
            problems.append(f"every test question needs a hint; missing in {no_hint}")
        for o in lesson.learning_objectives:
            n = sum(o.id in q.objective_ids for q in finals)
            if finals and n < 2:
                problems.append(f"objective {o.id} has {n} test question(s); give every objective at least 2")
        missing_remedial = sorted({o.id for o in lesson.learning_objectives} - {r.objective_id for r in lesson.remedials})
        if missing_remedial:
            problems.append(f"write one remedial per objective; missing for {missing_remedial}")
        no_visual = [s.section_id for s in lesson.sections
                     if s.section_type is not SectionType.INTRODUCTION
                     and not any(b.type is ContentBlockType.VISUAL for b in s.content_blocks)]
        if no_visual:
            problems.append(f"every section needs at least one visual block; missing in {no_visual}")
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
        context={"evidence_sources": {s.source_id for s in research.sources if s.evidence_passages}},
    )
    return complete_lesson(_to_lesson(draft, lesson_id, 1, videos), client), prompt.version


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
        context={"evidence_sources": {s.source_id for s in research.sources if s.evidence_passages}},
    )
    revised = _to_lesson(draft, lesson.lesson_id, next_version, list(lesson.videos))
    return complete_lesson(revised, client), prompt.version


# ------------------------------------------------- completing missing pieces


class _Check(ContractModel):
    section_id: str
    prompt: NonEmptyStr
    answer: NonEmptyStr
    why: NonEmptyStr


class _TryIt(ContractModel):
    title: NonEmptyStr
    instructions: NonEmptyStr
    hint: NonEmptyStr
    answer: NonEmptyStr


class _Completion(ContractModel):
    checks: list[_Check] = []
    activity: _TryIt | None = None


_S = {"type": "string"}
COMPLETION_SCHEMA = {
    "type": "object",
    "properties": {
        "checks": {"type": "array", "items": {"type": "object", "properties": {
            "section_id": _S, "prompt": _S, "answer": _S, "why": _S},
            "required": ["section_id", "prompt", "answer", "why"]}},
        "activity": {"type": ["object", "null"], "properties": {
            "title": _S, "instructions": _S, "hint": _S, "answer": _S},
            "required": ["title", "instructions", "hint", "answer"]},
    },
    "required": ["checks", "activity"],
}


def core_idea_sections(lesson: LessonVersion) -> list:
    """The two core-idea sections: titled 'Core idea ...', else the concept sections after the overview."""
    concepts = [s for s in lesson.sections if s.section_type is SectionType.CONCEPT_EXPLANATION]
    titled = [s for s in concepts if s.title.lower().startswith("core idea")]
    return titled or concepts[1:3]


def missing_parts(lesson: LessonVersion) -> tuple[list[str], bool]:
    """(core-idea sections without a check question, whether the 'Try it' activity is missing)."""
    checked = {q.section_id for q in lesson.assessments if q.kind is AssessmentKind.KNOWLEDGE_CHECK}
    sections = [s.section_id for s in core_idea_sections(lesson) if s.section_id not in checked]
    has_activity = any(a.is_mandatory for a in lesson.activities)
    has_worked = any(s.section_type is SectionType.WORKED_EXAMPLES for s in lesson.sections)
    return sections, has_worked and not has_activity


def complete_lesson(lesson: LessonVersion, client: LLMClient) -> LessonVersion:
    """Add the core-idea check questions and the 'Try it' activity if the model left them out.
    One small extra call, only when needed. If it fails, the lesson is kept as it is."""
    check_ids, need_activity = missing_parts(lesson)
    if not check_ids and not need_activity:
        return lesson
    worked = next((s for s in lesson.sections if s.section_type is SectionType.WORKED_EXAMPLES), None)
    shown = [s for s in lesson.sections if s.section_id in check_ids or (need_activity and s is worked)]
    request = {
        "learner_level": lesson.learner_level,
        "needed": {"check_sections": check_ids, "activity": need_activity},
        "sections": [s.model_dump(mode="json", include={"section_id", "title", "content_blocks"}) for s in shown],
    }

    def validate(out: _Completion) -> None:
        got = sorted(c.section_id for c in out.checks)
        if got != sorted(check_ids):
            raise LLMInvalidOutputError(f"write exactly one check for each of {check_ids}; got {got}")
        if need_activity and out.activity is None:
            raise LLMInvalidOutputError("needed.activity is true: write the activity")

    try:
        out = call_structured(client, system=load_prompt("generation/complete.md").text,
                              user="INPUT:\n" + to_prompt_json(request), schema=COMPLETION_SCHEMA,
                              output_model=_Completion, validate=validate)
    except LLMError:
        return lesson

    data = lesson.model_dump(mode="json")
    sections = {s.section_id: s for s in lesson.sections}
    all_objectives = [o.id for o in lesson.learning_objectives]
    next_q = max((int(q.question_id.split("-")[1]) for q in lesson.assessments), default=0)
    checks = []
    for c in out.checks:
        next_q += 1
        checks.append({
            "question_id": f"Q-{next_q:02d}", "section_id": c.section_id, "kind": "knowledge_check",
            "question_type": "short_answer", "prompt": c.prompt, "answer_key": c.answer, "explanation": c.why,
            "objective_ids": list(sections[c.section_id].objective_ids) or all_objectives[:1],
            "bloom_level": "understand",
        })
    data["assessments"] = checks + data["assessments"]
    if need_activity and out.activity and worked:
        data["activities"].append({
            "activity_id": f"ACT-{len(data['activities']) + 1:02d}", "section_id": worked.section_id,
            "title": out.activity.title, "instructions": out.activity.instructions, "duration_minutes": 2,
            "objective_ids": all_objectives, "is_mandatory": True,
            "hint": out.activity.hint, "answer": out.activity.answer,
        })
    try:
        return LessonVersion.model_validate(data)
    except ValueError:
        return lesson
