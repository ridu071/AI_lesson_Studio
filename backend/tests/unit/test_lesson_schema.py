import pytest
from pydantic import ValidationError

from app.schemas.enums import BloomLevel, bloom_rank
from app.schemas.lesson import LessonVersion


def test_valid_fixture_loads(lesson_data):
    lesson = LessonVersion.model_validate(lesson_data)
    assert lesson.lesson_id == "LES-001"
    assert sum(s.duration_minutes for s in lesson.sections) == 45
    assert lesson.cited_source_ids() == {"SRC-001", "SRC-002", "SRC-003"}


def test_lesson_is_immutable(lesson_data):
    lesson = LessonVersion.model_validate(lesson_data)
    with pytest.raises(ValidationError):
        lesson.title = "Changed after QC started"


# --- content hash: the basis of version integrity ---


def test_content_hash_is_stable(lesson_data):
    a = LessonVersion.model_validate(lesson_data)
    b = LessonVersion.model_validate(lesson_data)
    assert a.content_hash() == b.content_hash()
    assert len(a.content_hash()) == 64


def test_any_content_change_changes_the_hash(lesson_data):
    original = LessonVersion.model_validate(lesson_data).content_hash()
    lesson_data["sections"][2]["content_blocks"][0]["content"] += " (edited)"
    assert LessonVersion.model_validate(lesson_data).content_hash() != original


def test_version_number_alone_does_not_change_the_hash(lesson_data):
    # Same content under a new version number = a no-op revision, and we want to see that.
    original = LessonVersion.model_validate(lesson_data).content_hash()
    lesson_data["version"] = 2
    assert LessonVersion.model_validate(lesson_data).content_hash() == original


# --- structural problems are rejected ---


def test_duplicate_section_id_is_rejected(lesson_data):
    lesson_data["sections"][1]["section_id"] = "SEC-01"
    with pytest.raises(ValidationError, match="duplicate section id SEC-01"):
        LessonVersion.model_validate(lesson_data)


def test_claim_pointing_to_missing_section_is_rejected(lesson_data):
    lesson_data["claims"][0]["section_id"] = "SEC-99"
    with pytest.raises(ValidationError, match="CL-001 points to unknown section SEC-99"):
        LessonVersion.model_validate(lesson_data)


def test_question_pointing_to_missing_objective_is_rejected(lesson_data):
    lesson_data["assessments"][0]["objective_ids"] = ["LO-09"]
    with pytest.raises(ValidationError, match="Q-01 points to unknown objective LO-09"):
        LessonVersion.model_validate(lesson_data)


def test_lesson_without_objectives_is_rejected(lesson_data):
    lesson_data["learning_objectives"] = []
    with pytest.raises(ValidationError):
        LessonVersion.model_validate(lesson_data)


def test_unknown_field_is_rejected(lesson_data):
    lesson_data["aproved"] = True  # typo, and a field that must never exist anyway
    with pytest.raises(ValidationError):
        LessonVersion.model_validate(lesson_data)


def test_wrong_id_format_is_rejected(lesson_data):
    lesson_data["claims"][0]["source_ids"] = ["SEC-03"]  # a section ID where a source ID belongs
    with pytest.raises(ValidationError):
        LessonVersion.model_validate(lesson_data)


def test_blank_title_is_rejected(lesson_data):
    lesson_data["title"] = "    "
    with pytest.raises(ValidationError):
        LessonVersion.model_validate(lesson_data)


# --- quality problems are ACCEPTED, so QC can report them ---


def test_sixty_minute_lesson_is_accepted_for_qc_to_flag(lesson_data):
    lesson_data["sections"][2]["duration_minutes"] = 27  # total becomes 60
    lesson = LessonVersion.model_validate(lesson_data)
    assert sum(s.duration_minutes for s in lesson.sections) == 60


def test_citation_to_unknown_source_is_accepted_for_qc_to_flag(lesson_data):
    # Whether SRC-999 exists is a question about the research package: QC1's job.
    lesson_data["claims"][0]["source_ids"] = ["SRC-999"]
    lesson = LessonVersion.model_validate(lesson_data)
    assert "SRC-999" in lesson.cited_source_ids()


def test_bloom_levels_are_ordered():
    assert bloom_rank(BloomLevel.REMEMBER) == 1
    assert bloom_rank(BloomLevel.CREATE) == 6
    assert bloom_rank(BloomLevel.ANALYZE) > bloom_rank(BloomLevel.UNDERSTAND)
