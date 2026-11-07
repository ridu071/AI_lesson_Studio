"""Vocabulary for lesson content and research sources."""

from enum import StrEnum


class LearnerLevel(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class BloomLevel(StrEnum):
    """Bloom's Taxonomy cognitive levels, from lowest to highest."""

    REMEMBER = "remember"
    UNDERSTAND = "understand"
    APPLY = "apply"
    ANALYZE = "analyze"
    EVALUATE = "evaluate"
    CREATE = "create"


_BLOOM_RANK = {level: rank for rank, level in enumerate(BloomLevel, start=1)}


def bloom_rank(level: BloomLevel) -> int:
    """Higher number = higher cognitive level. REMEMBER is 1, CREATE is 6."""
    return _BLOOM_RANK[level]


class SectionType(StrEnum):
    """Lesson template sections (workflow section 6.2).

    A lesson may repeat or reorder sections. QC2 judges whether the structure works.
    """

    INTRODUCTION = "introduction"
    LEARNING_OBJECTIVES = "learning_objectives"
    CONCEPT_EXPLANATION = "concept_explanation"
    WORKED_EXAMPLES = "worked_examples"
    PRACTICAL_APPLICATION = "practical_application"
    KNOWLEDGE_CHECK = "knowledge_check"
    FINAL_ASSESSMENT = "final_assessment"
    SUMMARY = "summary"


class ContentBlockType(StrEnum):
    EXPLANATION = "explanation"  # short paragraph (max ~40 words)
    DEFINITION = "definition"
    EXAMPLE = "example"
    CODE = "code"
    DIAGRAM = "diagram"
    NOTE = "note"
    TAKEAWAY = "takeaway"  # one bold line that starts a chunk
    BULLETS = "bullets"  # list in `items`
    CALLOUT = "callout"  # `label` = Key idea | Common mistake | Tip
    VISUAL = "visual"  # drawn by the app from `visual_type` + structured spec


class VisualType(StrEnum):
    """How a visual is drawn. Chosen by content: process -> flowchart, parts -> labeled_diagram,
    differences -> table, events -> timeline, relationships -> concept_map, numbers -> chart,
    formulas -> formula_card, code -> code_snippet, abstract ideas -> analogy_scene."""

    FLOWCHART = "flowchart"
    LABELED_DIAGRAM = "labeled_diagram"
    TABLE = "table"
    TIMELINE = "timeline"
    CONCEPT_MAP = "concept_map"
    CHART = "chart"
    FORMULA_CARD = "formula_card"
    CODE_SNIPPET = "code_snippet"
    ANALOGY_SCENE = "analogy_scene"


class ClaimType(StrEnum):
    """What kind of statement a claim is. Decides how QC1 verifies it."""

    FACTUAL = "factual"  # needs evidence
    DEFINITION = "definition"  # needs evidence
    MATHEMATICAL = "mathematical"  # check by computation where possible
    OPINION = "opinion"  # recommendation, not a fact
    HYPOTHETICAL_EXAMPLE = "hypothetical_example"  # invented scenario for teaching
    INSTRUCTION = "instruction"  # "Now open your editor..."
    EXERCISE = "exercise"  # content of a student exercise


class AssessmentKind(StrEnum):
    KNOWLEDGE_CHECK = "knowledge_check"  # during the lesson
    FINAL = "final"  # final assessment


class QuestionType(StrEnum):
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    SHORT_ANSWER = "short_answer"
    SCENARIO = "scenario"  # a short new situation + options (scored like multiple choice)
    ORDER_STEPS = "order_steps"  # put `correct_order` in order
    MATCH_PAIRS = "match_pairs"  # match each left item to its right item (`pairs`)
    LABEL_VISUAL = "label_visual"  # match numbered parts of `visual` to labels (`pairs`)
    FILL_BLANK = "fill_blank"  # type the missing word(s); `accepted_answers` lists variants


class QuestionLevel(StrEnum):
    """Test difficulty band, easy to hard."""

    UNDERSTAND = "understand"
    APPLY = "apply"
    TRANSFER = "transfer"


class SourceType(StrEnum):
    WEBSITE = "website"
    BOOK = "book"
    VIDEO = "video"
    ACADEMIC = "academic"
    DOCUMENTATION = "documentation"


class AuthorityCategory(StrEnum):
    ACADEMIC = "academic"
    OFFICIAL = "official"
    GOVERNMENT = "government"
    EDUCATIONAL = "educational"
    REFERENCE = "reference"  # encyclopedias and other tertiary references
    INDUSTRY = "industry"
    NEWS = "news"
    COMMUNITY = "community"
    UNKNOWN = "unknown"


class AccessStatus(StrEnum):
    """Could we reach the source when we last tried?"""

    ACCESSIBLE = "accessible"
    INACCESSIBLE = "inaccessible"
    RESTRICTED = "restricted"  # e.g. paywall or login
    UNKNOWN = "unknown"


class ContentAccess(StrEnum):
    """How much of the source's actual content we have read.

    A book's metadata, or a video's title and description, does not prove what
    is inside it (workflow section 5.3).
    """

    FULL_TEXT = "full_text"
    EXCERPT = "excerpt"  # some passages, e.g. a transcript section or preview
    METADATA_ONLY = "metadata_only"  # title, author, description only
