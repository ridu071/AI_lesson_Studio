import json
from pathlib import Path

from app.generation.diff import diff_versions
from app.schemas.lesson import LessonVersion
from app.schemas.research import ResearchPackage

BASE = Path(__file__).resolve().parents[3] / "evaluation" / "benchmark_lessons" / "ml_intro"


def _load():
    lesson = json.loads((BASE / "lesson.json").read_text(encoding="utf-8"))
    research = ResearchPackage.model_validate_json((BASE / "research.json").read_text(encoding="utf-8"))
    return lesson, research


def test_only_the_version_number_differs_means_identical():
    data, research = _load()
    v1 = LessonVersion.model_validate(data)
    v2 = LessonVersion.model_validate({**data, "version": data["version"] + 1})
    d = diff_versions(v1, v2, research)
    assert d.identical and d.added == 0 and d.removed == 0


def test_changed_answer_key_shows_in_the_diff():
    data, research = _load()
    v1 = LessonVersion.model_validate(data)
    changed = json.loads(json.dumps(data))
    changed["version"] += 1
    changed["assessments"][2]["answer_key"] = "Unsupervised learning, a changed key."
    d = diff_versions(v1, LessonVersion.model_validate(changed), research)
    assert not d.identical
    assert d.added >= 1 and d.removed >= 1
    assert "+" in d.text and "a changed key" in d.text
