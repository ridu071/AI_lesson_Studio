"""The structured lesson document (workflow section 6.4).

This is the contract between lesson generation (which produces it) and QC
(which evaluates it).

Boundary rule (see docs/qc_specification.md):
- This schema rejects lessons that are STRUCTURALLY broken: wrong shape,
  duplicate IDs, or references to sections/objectives that do not exist
  inside the lesson.
- It deliberately ACCEPTS lessons with quality problems (a 60-minute lesson,
  a citation to a source that is not in the research package, an untested
  objective). Finding those is QC's job, and QC must report them as issues,
  not crash on them.
"""

import hashlib
import json

from pydantic import Field, HttpUrl, model_validator

from app.schemas.common import (
    ActivityId,
    ClaimId,
    ContractModel,
    LessonId,
    NonEmptyStr,
    ObjectiveId,
    QuestionId,
    SectionId,
    SourceId,
    VideoId,
    find_duplicates,
)
from app.schemas.enums import (
    AssessmentKind,
    BloomLevel,
    ClaimType,
    ContentBlockType,
    LearnerLevel,
    QuestionLevel,
    QuestionType,
    SectionType,
    VisualType,
)

Minutes = Field(ge=0, le=240)


class LearningObjective(ContractModel):
    id: ObjectiveId
    description: str = Field(min_length=5, max_length=500)
    bloom_level: BloomLevel


class ContentBlock(ContractModel):
    """One chunk of a section. Text blocks use `content`; bullets use `items`;
    visuals use `visual_type` + `elements` / `connections` / `rows` (+ `content` for code)."""

    type: ContentBlockType
    content: str = ""
    items: list[NonEmptyStr] = []
    label: str | None = None  # callouts: Key idea | Common mistake | Tip
    visual_type: VisualType | None = None
    elements: list[NonEmptyStr] = []  # nodes, parts, events, formula lines, scene parts
    connections: list[NonEmptyStr] = []  # "A -> B" or "A -> B: label"
    rows: list[list[str]] = []  # tables and charts; first row is the header
    caption: str | None = None  # one line: what to notice
    alt_text: str | None = None  # describes the visual for screen readers

    @model_validator(mode="after")
    def _has_what_its_type_needs(self) -> "ContentBlock":
        kind = self.type
        if kind is ContentBlockType.BULLETS and not self.items:
            raise ValueError("a bullets block needs items")
        if kind is ContentBlockType.VISUAL:
            if self.visual_type is None:
                raise ValueError("a visual block needs a visual_type")
            if not (self.elements or self.rows or self.content.strip()):
                raise ValueError("a visual block needs elements, rows or content")
            if not (self.caption and self.alt_text):
                raise ValueError("a visual block needs a caption and alt_text")
        elif kind is not ContentBlockType.BULLETS and not self.content.strip():
            raise ValueError(f"a {kind} block needs content")
        return self


class LessonSection(ContractModel):
    section_id: SectionId
    section_type: SectionType
    title: str = Field(min_length=1, max_length=200)
    # Authoritative time for the whole section, INCLUDING any activities and
    # questions placed inside it. Activity/question times are not added again.
    duration_minutes: int = Minutes
    objective_ids: list[ObjectiveId] = []
    content_blocks: list[ContentBlock] = Field(min_length=1)
    source_ids: list[SourceId] = []  # general references for the section


class Claim(ContractModel):
    """One atomic statement in the lesson that QC1 may need to verify."""

    claim_id: ClaimId
    section_id: SectionId
    text: NonEmptyStr
    claim_type: ClaimType
    source_ids: list[SourceId] = []


class Activity(ContractModel):
    activity_id: ActivityId
    section_id: SectionId
    title: NonEmptyStr
    instructions: NonEmptyStr
    duration_minutes: int = Minutes
    objective_ids: list[ObjectiveId] = []
    is_mandatory: bool = True
    hint: str | None = None  # shown in a collapsible "Hint"
    answer: str | None = None  # shown in a collapsible "Answer"


class WrongOption(ContractModel):
    """A wrong answer and the specific mix-up it represents."""

    option: NonEmptyStr
    misconception_id: NonEmptyStr
    misconception: NonEmptyStr


class AssessmentQuestion(ContractModel):
    question_id: QuestionId
    section_id: SectionId
    kind: AssessmentKind
    question_type: QuestionType
    prompt: NonEmptyStr
    options: list[NonEmptyStr] = []
    answer_key: NonEmptyStr
    explanation: NonEmptyStr
    objective_ids: list[ObjectiveId] = []
    bloom_level: BloomLevel
    # --- test questions ---
    level: QuestionLevel | None = None
    hint: str | None = None  # nudges toward the idea; never gives the answer
    wrong_options: list[WrongOption] = []
    review_section_id: SectionId | None = None  # where to go back to if answered wrongly
    correct_order: list[NonEmptyStr] = []  # order_steps
    pairs: list[list[str]] = []  # match_pairs / label_visual: [left, right]
    visual: ContentBlock | None = None  # optional visual (required for label_visual)
    accepted_answers: list[str] = []  # fill_blank: other acceptable spellings


class MixUp(ContractModel):
    misconception: NonEmptyStr
    correction: NonEmptyStr


class Remedial(ContractModel):
    """Shown after the test only if the learner scores below 70% on this objective:
    a different angle on the same idea."""

    objective_id: ObjectiveId
    takeaway: NonEmptyStr
    visual: ContentBlock
    explanation: list[NonEmptyStr] = Field(min_length=1, max_length=4)
    common_mix_ups: list[MixUp] = []


class LessonVideo(ContractModel):
    video_id: VideoId
    title: NonEmptyStr
    url: HttpUrl
    source_id: SourceId | None = None
    section_id: SectionId | None = None
    duration_minutes: int = Minutes
    is_mandatory: bool = False  # supplementary by default; mandatory ones count toward 45 min


class LessonVersion(ContractModel):
    """One immutable version of a lesson."""

    lesson_id: LessonId
    version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=200)
    learner_level: LearnerLevel = LearnerLevel.BEGINNER
    # What the generator says the lesson takes. QC compares it with the real total.
    stated_duration_minutes: int = Field(ge=1, le=240)
    learning_objectives: list[LearningObjective] = Field(min_length=1)
    sections: list[LessonSection] = Field(min_length=1)
    claims: list[Claim] = []
    activities: list[Activity] = []
    assessments: list[AssessmentQuestion] = []
    videos: list[LessonVideo] = []
    remedials: list[Remedial] = []

    @model_validator(mode="after")
    def _check_internal_references(self) -> "LessonVersion":
        problems: list[str] = []

        id_groups = (
            ("objective", [o.id for o in self.learning_objectives]),
            ("section", [s.section_id for s in self.sections]),
            ("claim", [c.claim_id for c in self.claims]),
            ("activity", [a.activity_id for a in self.activities]),
            ("assessment question", [q.question_id for q in self.assessments]),
            ("video", [v.video_id for v in self.videos]),
        )
        for label, ids in id_groups:
            problems += [f"duplicate {label} id {dup}" for dup in find_duplicates(ids)]

        section_ids = {s.section_id for s in self.sections}
        objective_ids = {o.id for o in self.learning_objectives}

        def check_section(owner: str, section_id: str | None) -> None:
            if section_id is not None and section_id not in section_ids:
                problems.append(f"{owner} points to unknown section {section_id}")

        def check_objectives(owner: str, ids: list[str]) -> None:
            problems.extend(
                f"{owner} points to unknown objective {oid}"
                for oid in ids
                if oid not in objective_ids
            )

        for s in self.sections:
            check_objectives(s.section_id, s.objective_ids)
        for c in self.claims:
            check_section(c.claim_id, c.section_id)
        for a in self.activities:
            check_section(a.activity_id, a.section_id)
            check_objectives(a.activity_id, a.objective_ids)
        for q in self.assessments:
            check_section(q.question_id, q.section_id)
            check_objectives(q.question_id, q.objective_ids)
        for v in self.videos:
            check_section(v.video_id, v.section_id)
        for q in self.assessments:
            check_section(f"{q.question_id} review link", q.review_section_id)
        for r in self.remedials:
            check_objectives("remedial", [r.objective_id])

        if problems:
            raise ValueError("Lesson structure is invalid: " + "; ".join(problems))
        return self

    def content_hash(self) -> str:
        """SHA-256 fingerprint of the lesson content.

        Audits and approvals store this hash, so any change to the content after
        an audit is detectable. The version number is excluded: two versions with
        identical content get the same hash, which reveals a no-op revision.
        """
        payload = self.model_dump(mode="json", exclude={"version"})
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def cited_source_ids(self) -> set[str]:
        """Every source ID the lesson refers to, from sections, claims and videos."""
        ids = {sid for s in self.sections for sid in s.source_ids}
        ids |= {sid for c in self.claims for sid in c.source_ids}
        ids |= {v.source_id for v in self.videos if v.source_id}
        return ids
