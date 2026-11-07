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
    """The fixture lesson as a model answer in the current lesson format:
    a visual in every section, 3 practice tasks and 5 final questions."""
    lesson_data = copy.deepcopy(lesson_data)
    for section in lesson_data["sections"]:
        section["content_blocks"].append({
            "type": "visual", "visual_type": "flowchart",
            "elements": ["Labelled data", "Train model", "Predict"],
            "connections": ["Labelled data -> Train model", "Train model -> Predict"],
            "caption": "Notice the order of the steps.", "alt_text": "Three boxes joined by arrows.",
        })
    practice = lesson_data["activities"][0]
    practice.update(duration_minutes=2, hint="Ask: does the data have labels?",
                    answer="Labelled data means supervised.")
    # The test: 10 hinted final questions, 3 types, at least 2 per objective.
    lesson_data["assessments"] = [q for q in lesson_data["assessments"] if q["kind"] != "final"]
    common = {"section_id": "SEC-07", "kind": "final", "explanation": "Labels make it supervised.",
              "hint": "Think about whether the data comes with answers.", "review_section_id": "SEC-03"}
    for n in range(10):
        objective = "LO-01" if n % 2 == 0 else "LO-02"
        if n % 3 == 0:
            q = {"question_type": "multiple_choice", "options": ["Supervised", "Unsupervised", "Neither", "Both"],
                 "answer_key": "Supervised",
                 "wrong_options": [{"option": "Unsupervised", "misconception_id": "M1",
                                    "misconception": "Thinks labels are not needed."}]}
        elif n % 3 == 1:
            q = {"question_type": "order_steps", "correct_order": ["Collect data", "Label it", "Train"],
                 "answer_key": "Collect data -> Label it -> Train"}
        else:
            q = {"question_type": "fill_blank", "answer_key": "labels", "accepted_answers": ["labelled data"]}
        lesson_data["assessments"].append(common | q | {
            "question_id": f"Q-{n + 10}", "prompt": f"Test question {n + 1} about ____ ?",
            "objective_ids": [objective], "bloom_level": "analyze", "level": "apply"})
    lesson_data["remedials"] = [{
        "objective_id": oid, "takeaway": "Labels are the answers the model learns from.",
        "visual": {"type": "visual", "visual_type": "analogy_scene",
                   "elements": ["Teacher with answer sheet = labels", "Student = model"],
                   "caption": "The answer sheet is what makes it supervised.", "alt_text": "A classroom scene."},
        "explanation": ["If every example comes with its answer, the model is supervised."],
        "common_mix_ups": [{"misconception": "Clusters are labels.", "correction": "Clusters are discovered."}],
    } for oid in ("LO-01", "LO-02")]
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
    # The video citation is removed, leaving the fact unsourced: still rejected.
    with pytest.raises(LLMInvalidOutputError, match="claims must cite a source"):
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


# --- lesson management ---


def test_rename_and_delete(project):
    project.rename("  My   HTTP lesson ")
    assert Project(project.folder).display_name == "My HTTP lesson"
    with pytest.raises(InputError):
        project.rename("   ")
    folder = project.folder
    project.delete()
    assert not folder.exists()


def test_same_topic_and_level_is_detected(project, tmp_path):
    same = validate_inputs("  machine   LEARNING ", OBJECTIVE)
    assert Project.find_existing(same, root=tmp_path).folder == project.folder
    other_level = validate_inputs("Machine learning", OBJECTIVE, "advanced")
    assert Project.find_existing(other_level, root=tmp_path) is None


def test_misplaced_block_text_is_repaired(lesson_data):
    draft = draft_from(lesson_data)
    draft["sections"][0]["content_blocks"] += [
        {"type": "callout", "label": "Tip: What do you already know about learning from data?"},
        {"type": "callout", "label": "Common mistake", "caption": "Thinking clusters are given in advance."},
    ]
    lesson = generator.GeneratedLesson.model_validate(draft)
    tip, mistake = lesson.sections[0].content_blocks[-2:]
    assert (tip.label, tip.content) == ("Tip", "What do you already know about learning from data?")
    assert (mistake.label, mistake.content) == ("Common mistake", "Thinking clusters are given in advance.")


def test_empty_callout_is_dropped_not_fatal(lesson_data):
    draft = draft_from(lesson_data)
    before = len(draft["sections"][0]["content_blocks"])
    draft["sections"][0]["content_blocks"].append({"type": "callout", "label": "Tip"})
    lesson = generator.GeneratedLesson.model_validate(draft)
    assert len(lesson.sections[0].content_blocks) == before


# --- visuals ---


def test_visual_specs_become_drawable_output():
    from app.generation.visuals import chart_data, table_markdown, to_dot
    from app.schemas.lesson import ContentBlock

    flow = ContentBlock(type="visual", visual_type="flowchart", elements=["Client sends request", "Server replies"],
                        connections=['Client sends request -> Server replies: "200 OK"'],
                        caption="Order matters.", alt_text="Two boxes and an arrow.")
    dot = to_dot(flow)
    assert dot.startswith("digraph") and "rankdir=LR" in dot and "->" in dot and '\\"200 OK\\"' in dot
    assert table_markdown([["Code", "Meaning"], ["404", "Not found | missing"]]).splitlines()[2] == \
        "| 404 | Not found \| missing |"
    assert chart_data([["Year", "Count"], ["2020", "3"], ["2021", "5.5"]]) == ("Count", ["2020", "2021"], [3.0, 5.5])
    assert chart_data([["A", "B"], ["x", "not a number"]]) is None


def test_visual_block_needs_caption_and_alt_text():
    from pydantic import ValidationError as VE
    from app.schemas.lesson import ContentBlock
    with pytest.raises(VE, match="caption and alt_text"):
        ContentBlock(type="visual", visual_type="table", rows=[["a"], ["b"]])


def test_markdown_export_includes_rich_blocks(lesson_data, research_data):
    from app.schemas.lesson import LessonVersion
    draft = draft_from(lesson_data)
    draft["sections"][0]["content_blocks"] += [
        {"type": "takeaway", "content": "Labels make learning supervised."},
        {"type": "bullets", "items": ["Input", "Label"]},
        {"type": "callout", "label": "Common mistake", "content": "Thinking clusters are given."},
    ]
    lesson = LessonVersion(lesson_id="LES-001", version=1, **draft)
    text = render_lesson_markdown(lesson, ResearchPackage.model_validate(research_data))
    assert "**Labels make learning supervised.**" in text and "- Input" in text
    assert "> **Common mistake:** Thinking clusters are given." in text
    assert "*Visual (flowchart): Notice the order of the steps.*" in text
    assert "*Hint:* Ask: does the data have labels?" in text and "## Practice answers" in text


def test_test_section_always_has_exactly_ten_questions(lesson_data, research_data):
    research = ResearchPackage.model_validate(research_data)
    too_many = draft_from(lesson_data)
    extra = [q | {"question_id": f"Q-{40 + i}"} for i, q in enumerate(too_many["assessments"][-2:])]
    too_many["assessments"] += extra  # 12 test questions
    lesson, _ = generator.generate_lesson(title="ML", objective=OBJECTIVE, research=research,
                                          video_minutes={}, client=LessonLLM([too_many]), lesson_id="LES-001")
    assert sum(q.kind == "final" for q in lesson.assessments) == 10

    too_few = draft_from(lesson_data)
    finals = [q for q in too_few["assessments"] if q["kind"] == "final"]
    too_few["assessments"] = [q for q in too_few["assessments"] if q["kind"] != "final"] + finals[:8]
    llm = LessonLLM([too_few, draft_from(lesson_data)])
    lesson, _ = generator.generate_lesson(title="ML", objective=OBJECTIVE, research=research,
                                          video_minutes={}, client=llm, lesson_id="LES-001")
    assert sum(q.kind == "final" for q in lesson.assessments) == 10
    assert "you wrote 8 test questions; the Test section needs exactly 10" in llm.calls[-1]["user"]


def test_book_citations_are_removed_and_missing_hints_filled(lesson_data, research_data):
    draft = draft_from(lesson_data)
    draft["claims"][0]["source_ids"] = ["SRC-001", "SRC-003"]  # SRC-003 is a video (no passages)
    final = next(q for q in draft["assessments"] if q["kind"] == "final")
    final["hint"] = None
    lesson, _ = generator.generate_lesson(title="ML", objective=OBJECTIVE,
                                          research=ResearchPackage.model_validate(research_data),
                                          video_minutes={}, client=LessonLLM([draft]), lesson_id="LES-001")
    assert lesson.claims[0].source_ids == ["SRC-001"]
    filled = next(q for q in lesson.assessments if q.kind == "final")
    assert filled.hint.startswith("Think back to the section")


# --- student downloads ---


def test_pdf_notes_and_summary_image(lesson_data, research_data):
    import io as _io
    from PIL import Image
    from app.generation.exports import lesson_pdf, summary_image, summary_points
    from app.schemas.lesson import LessonVersion

    lesson = LessonVersion(lesson_id="LES-001", version=1, **draft_from(lesson_data))
    pdf = lesson_pdf(lesson, ResearchPackage.model_validate(research_data))
    assert pdf.startswith(b"%PDF-") and len(pdf) > 5_000
    png = summary_image(lesson)
    image = Image.open(_io.BytesIO(png))
    assert image.format == "PNG" and image.size == (1080, 1350)
    assert summary_points(lesson)["takeaways"]  # falls back to section takeaways for older lessons


def test_pdf_text_contains_every_section_and_the_answer_key(lesson_data, research_data):
    pypdf = pytest.importorskip("pypdf")
    import io as _io
    from app.generation.exports import lesson_pdf
    from app.schemas.lesson import LessonVersion

    lesson = LessonVersion(lesson_id="LES-001", version=1, **draft_from(lesson_data))
    text = " ".join(page.extract_text() for page in pypdf.PdfReader(_io.BytesIO(
        lesson_pdf(lesson, ResearchPackage.model_validate(research_data)))).pages)
    assert all(s.title[:20] in text for s in lesson.sections if s.section_type != "learning_objectives")
    assert "Answer key" in text
