"""Offline tests for research safety, generation checks, rendering and the workflow."""

import copy
import json
import zipfile
import io

import pytest

from app.generation import generator
from app.generation.render import render_lesson_markdown
from app.llm.base import LLMInvalidOutputError, LLMUnavailableError
from app.research.engine import ResearchPlan, ResearchResult
from app.research.http import ResearchSourceError, get_json
from app.schemas.research import ResearchPackage
from app import workflow
from app.workflow import InputError, Project, StepFailed, validate_inputs
from tests.fakes import FakeLLM

OBJECTIVE = "Differentiate supervised and unsupervised learning and identify applications of both."


def draft_from(lesson_data: dict) -> dict:
    lesson_data = copy.deepcopy(lesson_data)
    return {k: v for k, v in lesson_data.items() if k not in ("lesson_id", "version", "videos")}


class LessonLLM(FakeLLM):
    """FakeLLM that also answers lesson generation/revision calls."""

    def __init__(self, lesson_answers, **kw):
        super().__init__(**kw)
        self._answers[id(generator.LESSON_SCHEMA)] = list(lesson_answers)


# --- inputs ---


@pytest.mark.parametrize("title, objective", [("", OBJECTIVE), ("ML", ""), ("ML", "too short"),
                                              ("!!!", OBJECTIVE), ("Machine learning", "a b c d e f g h")])
def test_bad_inputs_are_rejected_before_anything_runs(title, objective):
    with pytest.raises(InputError):
        validate_inputs(title, objective)


def test_one_word_title_and_whitespace_are_fine():
    inputs = validate_inputs("  Photosynthesis ", "Describe   the inputs and outputs of photosynthesis.")
    assert inputs.title == "Photosynthesis"
    assert inputs.objective == "Describe the inputs and outputs of photosynthesis."


# --- research safety ---


@pytest.mark.parametrize("url", ["http://en.wikipedia.org/w/api.php", "https://169.254.169.254/latest",
                                 "https://localhost/admin", "https://evil.example.com/x"])
def test_research_can_only_reach_allowlisted_https_hosts(url):
    with pytest.raises(ResearchSourceError, match="blocked"):
        get_json(url, {})


# --- generation checks ---


def test_generated_lesson_gets_code_attached_videos(lesson_data, research_data):
    research = ResearchPackage.model_validate(research_data)
    llm = LessonLLM([draft_from(lesson_data)])
    lesson, _ = generator.generate_lesson(title="ML", objective=OBJECTIVE, research=research,
                                          video_minutes={"SRC-003": 7}, client=llm, lesson_id="LES-001")
    assert lesson.version == 1
    assert [(v.source_id, v.duration_minutes, v.is_mandatory) for v in lesson.videos] == [("SRC-003", 7, False)]


def test_draft_citing_a_metadata_only_source_is_rejected(lesson_data, research_data):
    bad = draft_from(lesson_data)
    bad["claims"][0]["source_ids"] = ["SRC-003"]  # a video: no passages, cannot be evidence
    llm = LessonLLM([bad, bad])
    with pytest.raises(LLMInvalidOutputError, match="only sources with evidence passages"):
        generator.generate_lesson(title="ML", objective=OBJECTIVE,
                                  research=ResearchPackage.model_validate(research_data),
                                  video_minutes={}, client=llm, lesson_id="LES-001")


def test_draft_over_45_minutes_is_sent_back_and_fixed(lesson_data, research_data):
    long = draft_from(lesson_data)
    long["sections"][2]["duration_minutes"] = 30
    llm = LessonLLM([long, draft_from(lesson_data)])
    lesson, _ = generator.generate_lesson(title="ML", objective=OBJECTIVE,
                                          research=ResearchPackage.model_validate(research_data),
                                          video_minutes={}, client=llm, lesson_id="LES-001")
    assert sum(s.duration_minutes for s in lesson.sections) == 45
    assert "must total 40-45" in llm.calls[-1]["user"]  # the retry told the model why


def test_references_come_from_research_not_the_model(lesson_data, research_data):
    from app.schemas.lesson import LessonVersion
    lesson = LessonVersion.model_validate(lesson_data)
    text = render_lesson_markdown(lesson, ResearchPackage.model_validate(research_data))
    assert "## References" in text and "https://example.org/ml/intro" in text
    assert "Supplementary videos (optional" in text
    assert "## Answer key" in text


# --- workflow: checkpoints, retry, versions, export ---


@pytest.fixture
def project(tmp_path, monkeypatch, research_data):
    package = ResearchPackage.model_validate(research_data)
    plan = ResearchPlan(key_concepts=["supervised learning"], wikipedia_queries=["Machine learning"],
                        book_query="machine learning", video_queries=["machine learning"])
    monkeypatch.setattr(workflow, "run_research",
                        lambda *a, **k: ResearchResult(plan=plan, package=package, video_minutes={}))
    return Project.create(validate_inputs("Machine learning", OBJECTIVE), root=tmp_path)


def settings():
    from app.core.config import Settings
    return Settings(_env_file=None)


def test_full_run_saves_every_step(project, lesson_data):
    project.run_remaining(LessonLLM([draft_from(lesson_data)]), settings())
    assert {s["status"] for s in project.meta["steps"].values()} == {"done"}
    assert project.audits()[2].decision == "eligible_for_instructor_review"
    assert (project.folder / "research.json").exists() and (project.folder / "lessons" / "v1.json").exists()


def test_failed_step_keeps_earlier_work_and_can_be_retried(project, lesson_data):
    with pytest.raises(StepFailed, match="model timed out"):
        project.run_remaining(LessonLLM([LLMUnavailableError("model timed out")]), settings())
    assert project.step("research")["status"] == "done"  # research was not lost
    assert project.step("generation")["status"] == "failed"
    assert project.next_step() == "generation"
    reloaded = Project(project.folder)  # survives a restart
    reloaded.run_remaining(LessonLLM([draft_from(lesson_data)]), settings())
    assert reloaded.next_step() is None and reloaded.current_version == 1


def test_instructor_edit_is_a_new_version_and_old_one_is_kept(project, lesson_data):
    project.run_remaining(LessonLLM([draft_from(lesson_data)]), settings())
    data = project.lesson().model_dump(mode="json")
    data["sections"][0]["content_blocks"][0]["content"] = "An edited introduction for my class."
    edited = project.save_edit(data, "Rewrote the intro")
    assert edited.version == 2
    assert "Rewrote" not in project.lesson(1).sections[0].content_blocks[0].content
    assert project.lesson(1).sections[0].content_blocks[0].content != edited.sections[0].content_blocks[0].content
    assert project.step("qc")["status"] == "pending"  # v2 must be checked again
    assert project.audits(1) is not None and project.audits(2) is None


def test_saving_without_changes_is_refused(project, lesson_data):
    project.run_remaining(LessonLLM([draft_from(lesson_data)]), settings())
    with pytest.raises(InputError, match="Nothing changed"):
        project.save_edit(project.lesson().model_dump(mode="json"), "")


def test_apply_recommendations_creates_and_checks_a_new_version(project, lesson_data):
    project.run_remaining(LessonLLM([draft_from(lesson_data)]), settings())
    revised = draft_from(lesson_data)
    revised["sections"][0]["content_blocks"][0]["content"] += " Now with a clearer hook."
    project.apply_recommendations([], "Make the introduction more engaging.", LessonLLM([revised]), settings())
    assert project.current_version == 2
    assert project.meta["versions"][-1]["origin"] == "ai_revision"
    assert project.audits(2) is not None


def test_export_contains_lesson_references_and_both_reports(project, lesson_data):
    project.run_remaining(LessonLLM([draft_from(lesson_data)]), settings())
    names = zipfile.ZipFile(io.BytesIO(project.export_zip())).namelist()
    assert {"v1/lesson.md", "v1/references.md", "v1/qc1_factual_audit.md",
            "v1/qc2_instructional_audit.md", "v1/qc_audits.json"} <= set(names)
    qc1 = project.export_files()["qc1_factual_audit.md"]
    assert qc1.startswith("# QC1 - Factual accuracy - audit report")
    assert json.loads(project.export_files()["qc_audits.json"])["release"]["decision"]


def test_model_id_slips_are_renumbered_consistently(lesson_data):
    draft = draft_from(lesson_data)
    for n, claim in enumerate(draft["claims"], start=1):
        claim["claim_id"] = f"CLM-{n}"          # wrong prefix, as a model once produced
    draft["sections"][2]["section_id"] = "S3"    # and a wrong section id ...
    for item in draft["claims"] + draft["activities"] + draft["assessments"]:
        if item["section_id"] == "SEC-03":
            item["section_id"] = "S3"            # ... with its references
    lesson = generator.GeneratedLesson.model_validate(draft)
    assert [c.claim_id for c in lesson.claims][:2] == ["CL-01", "CL-02"]
    assert lesson.sections[2].section_id == "SEC-03"
    assert {c.section_id for c in lesson.claims} <= {s.section_id for s in lesson.sections}
