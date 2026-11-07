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
    EXPLANATION = "explanation"
    DEFINITION = "definition"
    EXAMPLE = "example"
    CODE = "code"
    DIAGRAM = "diagram"
    NOTE = "note"


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
    SCENARIO = "scenario"


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
