"""The lesson workflow: inputs -> research -> generation -> QC -> review/edit -> export.

Error handling (assignment section 4):
- Inputs are validated before anything runs.
- Every step saves its result to disk the moment it succeeds (checkpoint),
  so a later failure never loses earlier work.
- A failed step records its error and can be retried; retrying resumes from
  the first unfinished step.
- Every lesson change (AI revision or instructor edit) is a NEW version file.
  Old versions and their QC reports are never overwritten.

Storage: data/projects/<project_id>/
    project.json          inputs, step status, version history
    research.json         research package + plan
    lessons/v<N>.json     each lesson version
    audits/v<N>.json      QC1 + QC2 + decision for that exact version
"""

import io
import json
import re
import secrets
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.core.config import BACKEND_DIR, Settings
from app.generation.generator import generate_lesson, revise_lesson
from app.generation.render import render_lesson_markdown, render_references
from app.llm.base import LLMClient, LLMError
from app.modules.qc.engine import run_full_qc
from app.modules.qc.reporting import render_audit_report
from app.modules.qc.schemas import AuditReport, QCInput, ReleaseResult
from app.research.engine import InsufficientResearchError, ResearchPlan, run_research
from app.research.http import ResearchSourceError
from app.schemas.enums import LearnerLevel
from app.schemas.lesson import LessonVersion
from app.schemas.research import ResearchPackage

DATA_DIR = BACKEND_DIR.parent / "data" / "projects"
STEPS = ("research", "generation", "qc")


class InputError(ValueError):
    """The instructor's inputs are invalid; nothing was run."""


class StepFailed(Exception):
    """A step failed; its error is saved and it can be retried."""


class LessonInputs(BaseModel):
    title: str = Field(min_length=3, max_length=150)
    objective: str = Field(min_length=15, max_length=600)
    learner_level: LearnerLevel = LearnerLevel.BEGINNER

    @field_validator("title", "objective", mode="before")
    @classmethod
    def _clean(cls, value: Any) -> Any:
        return " ".join(value.split()) if isinstance(value, str) else value

    @field_validator("title")
    @classmethod
    def _title_has_a_word(cls, value: str) -> str:
        if not re.search(r"[A-Za-z]{2,}", value):
            raise ValueError("must contain at least one real word")
        return value

    @field_validator("objective")
    @classmethod
    def _objective_is_a_sentence(cls, value: str) -> str:
        if len(re.findall(r"[A-Za-z]{2,}", value)) < 3:
            raise ValueError("must be a phrase of at least three real words")
        return value


def validate_inputs(title: str, objective: str, learner_level: str = "beginner") -> LessonInputs:
    try:
        return LessonInputs(title=title or "", objective=objective or "", learner_level=learner_level)
    except ValidationError as exc:
        messages = []
        for err in exc.errors():
            field = {"title": "Lesson title", "objective": "Learning objective"}.get(err["loc"][0], err["loc"][0])
            text = err["msg"].replace("String should have", "must have").replace("Value error, ", "")
            messages.append(f"{field} {text}.")
        raise InputError(" ".join(messages)) from exc


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Project:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.meta: dict = json.loads((folder / "project.json").read_text(encoding="utf-8"))

    # ---------------------------------------------------------- creation/load

    @classmethod
    def create(cls, inputs: LessonInputs, root: Path = DATA_DIR) -> "Project":
        project_id = f"{datetime.now(UTC):%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
        folder = root / project_id
        (folder / "lessons").mkdir(parents=True)
        (folder / "audits").mkdir()
        meta = {
            "project_id": project_id, "lesson_id": "LES-001", "created_at": _now(),
            "inputs": inputs.model_dump(mode="json"),
            "steps": {s: {"status": "pending", "error": None, "updated_at": None} for s in STEPS},
            "versions": [], "dismissed": {},
        }
        (folder / "project.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return cls(folder)

    @classmethod
    def list_all(cls, root: Path = DATA_DIR) -> list["Project"]:
        if not root.exists():
            return []
        found = [cls(p) for p in root.iterdir() if (p / "project.json").exists()]
        return sorted(found, key=lambda p: p.meta["created_at"], reverse=True)

    def save_meta(self) -> None:
        tmp = self.folder / "project.json.tmp"
        tmp.write_text(json.dumps(self.meta, indent=2), encoding="utf-8")
        # Atomic replace: never a half-written file. On Windows, antivirus or the
        # search indexer can briefly lock a just-written file, so retry a moment.
        for attempt in range(20):
            try:
                tmp.replace(self.folder / "project.json")
                return
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.05)

    # ---------------------------------------------------------------- reading

    @property
    def inputs(self) -> LessonInputs:
        return LessonInputs(**self.meta["inputs"])

    @property
    def current_version(self) -> int | None:
        return self.meta["versions"][-1]["version"] if self.meta["versions"] else None

    def research(self) -> tuple[ResearchPackage, ResearchPlan, dict[str, int]] | None:
        path = self.folder / "research.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return (ResearchPackage.model_validate(data["package"]), ResearchPlan.model_validate(data["plan"]),
                data["video_minutes"])

    def lesson(self, version: int | None = None) -> LessonVersion | None:
        version = version or self.current_version
        path = self.folder / "lessons" / f"v{version}.json"
        return LessonVersion.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None

    def audits(self, version: int | None = None) -> tuple[AuditReport, AuditReport, ReleaseResult | None] | None:
        version = version or self.current_version
        path = self.folder / "audits" / f"v{version}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        release = ReleaseResult.model_validate(data["release"]) if data["release"] else None
        return AuditReport.model_validate(data["qc1"]), AuditReport.model_validate(data["qc2"]), release

    def qc_input(self, version: int | None = None) -> QCInput:
        package, _, _ = self.research()
        return QCInput(request_objective=self.inputs.objective, lesson=self.lesson(version), research=package)

    def step(self, name: str) -> dict:
        return self.meta["steps"][name]

    def next_step(self) -> str | None:
        return next((s for s in STEPS if self.step(s)["status"] != "done"), None)

    # ---------------------------------------------------------------- writing

    def _set(self, name: str, status: str, error: str | None = None) -> None:
        self.meta["steps"][name] = {"status": status, "error": error, "updated_at": _now()}
        self.save_meta()

    def _add_version(self, lesson: LessonVersion, origin: str, note: str = "") -> None:
        path = self.folder / "lessons" / f"v{lesson.version}.json"
        if path.exists():
            raise RuntimeError(f"version {lesson.version} already exists; versions are never overwritten")
        path.write_text(lesson.model_dump_json(indent=2), encoding="utf-8")
        self.meta["versions"].append({"version": lesson.version, "origin": origin, "note": note,
                                      "created_at": _now(), "content_hash": lesson.content_hash()})
        self.meta["steps"]["qc"] = {"status": "pending", "error": None, "updated_at": _now()}
        self.save_meta()

    def _run(self, name: str, action) -> None:
        self._set(name, "running")
        try:
            action()
        except (LLMError, ResearchSourceError, InsufficientResearchError, ValidationError, ValueError) as exc:
            self._set(name, "failed", f"{type(exc).__name__}: {exc}"[:1500])
            raise StepFailed(self.step(name)["error"]) from exc
        self._set(name, "done")

    # ------------------------------------------------------------------ steps

    def run_research(self, client: LLMClient, settings: Settings) -> None:
        def action() -> None:
            key = settings.youtube_api_key.get_secret_value() if settings.youtube_api_key else ""
            result = run_research(self.inputs.title, self.inputs.objective, client, youtube_api_key=key)
            data = {"package": result.package.model_dump(mode="json"), "plan": result.plan.model_dump(),
                    "video_minutes": result.video_minutes, "prompt_version": result.prompt_version}
            (self.folder / "research.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
        self._run("research", action)

    def run_generation(self, client: LLMClient) -> None:
        def action() -> None:
            package, _, minutes = self.research()
            lesson, _ = generate_lesson(
                title=self.inputs.title, objective=self.inputs.objective, research=package,
                video_minutes=minutes, client=client, lesson_id=self.meta["lesson_id"],
                learner_level=self.inputs.learner_level)
            self._add_version(lesson, "generated")
        self._run("generation", action)

    def run_qc(self, client: LLMClient, settings: Settings) -> None:
        def action() -> None:
            run = run_full_qc(self.qc_input(), client, settings=settings)
            data = {"qc1": run.qc1.model_dump(mode="json"), "qc2": run.qc2.model_dump(mode="json"),
                    "release": run.release.model_dump(mode="json") if run.release else None}
            (self.folder / "audits" / f"v{self.current_version}.json").write_text(
                json.dumps(data, indent=2), encoding="utf-8")
            if run.release is None:
                raise ValueError(run.qc1.error_message or run.qc2.error_message or "QC could not finish")
        self._run("qc", action)

    def run_remaining(self, client: LLMClient, settings: Settings, progress=None) -> None:
        """Run (or resume) every unfinished step in order; stops at the first failure."""
        while (step := self.next_step()) is not None:
            if progress:
                progress(step)
            if step == "research":
                self.run_research(client, settings)
            elif step == "generation":
                self.run_generation(client)
            else:
                self.run_qc(client, settings)

    # ------------------------------------------------------ review and edits

    def apply_recommendations(self, issue_ids: list[str], note: str, client: LLMClient,
                              settings: Settings) -> None:
        audits = self.audits()
        if not audits:
            raise StepFailed("Run QC before applying recommendations.")
        issues = [i for i in audits[0].issues + audits[1].issues if i.issue_id in issue_ids]
        if not issues and not note.strip():
            raise StepFailed("Select at least one issue, or write an instruction.")
        package, _, _ = self.research()

        def action() -> None:
            revised, _ = revise_lesson(lesson=self.lesson(), objective=self.inputs.objective,
                                       research=package, issues=issues, instructor_note=note, client=client)
            self._add_version(revised, "ai_revision", f"Applied {', '.join(issue_ids) or 'instructor note'}"
                              + (f": {note}" if note else ""))
        self._run("generation", action)
        self.run_qc(client, settings)

    def save_edit(self, lesson_data: dict, note: str) -> LessonVersion:
        """An instructor edit becomes the next version. QC must be re-run for it."""
        current = self.lesson()
        data = lesson_data | {"lesson_id": current.lesson_id, "version": current.version + 1}
        try:
            edited = LessonVersion.model_validate(data)
        except ValidationError as exc:
            raise InputError(f"The edit is not valid: {exc.errors()[0]['msg']}") from exc
        if edited.content_hash() == current.content_hash():
            raise InputError("Nothing changed, so no new version was saved.")
        self._add_version(edited, "instructor_edit", note)
        return edited

    def dismiss(self, issue_id: str) -> None:
        self.meta["dismissed"].setdefault(str(self.current_version), []).append(issue_id)
        self.save_meta()

    def dismissed(self) -> set[str]:
        return set(self.meta["dismissed"].get(str(self.current_version), []))

    # ---------------------------------------------------------------- export

    def export_files(self) -> dict[str, str]:
        lesson = self.lesson()
        package, _, _ = self.research()
        files = {
            "lesson.md": render_lesson_markdown(lesson, package),
            "references.md": "\n".join(render_references(lesson, package)),
            "lesson.json": lesson.model_dump_json(indent=2),
            "research.json": package.model_dump_json(indent=2),
        }
        audits = self.audits()
        if audits:
            qc_input = self.qc_input()
            files["qc1_factual_audit.md"] = render_audit_report(qc_input, audits[0])
            files["qc2_instructional_audit.md"] = render_audit_report(qc_input, audits[1])
            files["qc_audits.json"] = json.dumps({
                "qc1": audits[0].model_dump(mode="json"), "qc2": audits[1].model_dump(mode="json"),
                "release": audits[2].model_dump(mode="json") if audits[2] else None}, indent=2)
        return files

    def export_zip(self) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in self.export_files().items():
                archive.writestr(f"v{self.current_version}/{name}", content)
        return buffer.getvalue()
