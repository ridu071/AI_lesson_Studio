"""The QC benchmark (workflow sections 19.2, 20.2 and 25).

A benchmark case = a base lesson + edits that introduce known problems +
what a human reviewer expects QC to report. The runner measures:
- recall:    of the problems we planted, how many did QC find?
- precision: of the issues QC reported, how many were real?
- blocking:  did QC block exactly the lessons that must be blocked?

Cases that need evaluators which have not run (e.g. the LLM claim verifier
before Step 6) are SKIPPED and reported, never silently counted as passes.
"""

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from app.core.config import BACKEND_DIR
from app.evaluation.patch import apply_patch
from app.modules.qc.engine import QCRunResult
from app.modules.qc.enums import Evaluator, IssueType, ReleaseDecision
from app.modules.qc.policy import ISSUE_POLICY
from app.modules.qc.schemas import QCInput, QCIssue
from app.modules.qc.scoring.rubrics import RUBRICS
from app.schemas.common import ClaimId, ContractModel, NonEmptyStr, ObjectiveId, SectionId

EVALUATION_DIR = BACKEND_DIR.parent / "evaluation"
CASE_FOLDERS = ("control_cases", "factual_test_cases", "instructional_test_cases")

# Every evaluator some rubric category needs. Only when all of these ran can
# the exact release decision be compared (otherwise categories stay unevaluated).
_ALL_RUBRIC_EVALUATORS = frozenset(
    e for rubric in RUBRICS.values() for category in rubric for e in category.requires
)

QCRunner = Callable[[QCInput], QCRunResult]


# ------------------------------------------------------------------ case format


class Mutation(ContractModel):
    op: Literal["add", "replace", "remove"]
    path: str = Field(pattern=r"^/(lesson|research|request_objective)(/.*)?$")
    value: Any = None

    @model_validator(mode="after")
    def _value_present(self) -> "Mutation":
        if self.op != "remove" and "value" not in self.model_fields_set:
            raise ValueError(f"'{self.op}' at {self.path} needs a value")
        return self


class ExpectedIssue(ContractModel):
    """An issue QC must report. Location fields that are given must match."""

    issue_type: IssueType
    section_id: SectionId | None = None
    claim_id: ClaimId | None = None
    objective_id: ObjectiveId | None = None
    # Only expected when this evaluator runs (e.g. a research gap that only
    # the LLM gap detector can see). Otherwise it is neither required nor penalised.
    needs: Evaluator | None = None

    def matches(self, issue: QCIssue) -> bool:
        return issue.issue_type is self.issue_type and all(
            expected is None or expected == getattr(issue, name)
            for name, expected in (
                ("section_id", self.section_id),
                ("claim_id", self.claim_id),
                ("objective_id", self.objective_id),
            )
        )

    def label(self) -> str:
        where = self.claim_id or self.objective_id or self.section_id
        return f"{self.issue_type}" + (f" @ {where}" if where else "")

    @property
    def must_block(self) -> bool:
        policy = ISSUE_POLICY[self.issue_type]
        return policy.hard_gate or policy.severity == "critical"


class Expected(ContractModel):
    decision: ReleaseDecision  # what a human reviewer would decide
    issues: list[ExpectedIssue] = []  # exactly the issues QC should report
    # Defensible extra findings: not required, and not counted as false alarms.
    # Decided when the case is written, never added to make a run pass.
    acceptable: list[ExpectedIssue] = []


class BenchmarkCase(ContractModel):
    case_id: str = Field(pattern=r"^[A-Z]-\d{3}$")
    title: NonEmptyStr
    rationale: NonEmptyStr  # why this is (or is not) a problem
    base: NonEmptyStr  # folder in benchmark_lessons/
    requires_evaluators: list[Evaluator] = []
    mutations: list[Mutation] = []
    expected: Expected


def load_cases(root: Path = EVALUATION_DIR) -> list[BenchmarkCase]:
    cases = [
        BenchmarkCase.model_validate_json(path.read_text(encoding="utf-8"))
        for folder in CASE_FOLDERS
        for path in sorted((root / folder).glob("*.json"))
    ]
    ids = [c.case_id for c in cases]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ValueError(f"duplicate benchmark case ids: {sorted(duplicates)}")
    return sorted(cases, key=lambda c: c.case_id)


def build_input(case: BenchmarkCase, root: Path = EVALUATION_DIR) -> QCInput:
    base_dir = root / "benchmark_lessons" / case.base

    def read(name: str) -> Any:
        return json.loads((base_dir / name).read_text(encoding="utf-8"))

    document = {
        "request_objective": read("request.json")["request_objective"],
        "lesson": read("lesson.json"),
        "research": read("research.json"),
    }
    patched = apply_patch(document, [m.model_dump() for m in case.mutations])
    return QCInput.model_validate(patched)


# ---------------------------------------------------------------------- results


@dataclass(frozen=True)
class CaseResult:
    case: BenchmarkCase
    skipped_reason: str | None = None
    actual_decision: ReleaseDecision | None = None
    found: list[ExpectedIssue] = field(default_factory=list)  # true positives
    missed: list[ExpectedIssue] = field(default_factory=list)  # false negatives
    unexpected: list[QCIssue] = field(default_factory=list)  # false positives
    decision_checked: bool = False  # exact decision compared only when all evaluators ran
    error: str | None = None  # an audit could not finish (e.g. LLM timeout)

    @property
    def ran(self) -> bool:
        return self.skipped_reason is None

    @property
    def scored(self) -> bool:
        """Ran and produced a decision, so its issues can be counted."""
        return self.ran and self.error is None

    @property
    def expected_block(self) -> bool:
        return self.case.expected.decision is ReleaseDecision.BLOCKED

    @property
    def actual_block(self) -> bool:
        return self.actual_decision is ReleaseDecision.BLOCKED

    @property
    def passed(self) -> bool:
        if not self.scored or self.missed or self.unexpected:
            return False
        if self.decision_checked:
            return self.actual_decision is self.case.expected.decision
        return self.actual_block == self.expected_block


def run_case(
    case: BenchmarkCase,
    runner: QCRunner,
    evaluators_available: frozenset[Evaluator],
    root: Path = EVALUATION_DIR,
) -> CaseResult:
    missing = set(case.requires_evaluators) - evaluators_available
    if missing:
        return CaseResult(case, skipped_reason="needs " + ", ".join(sorted(missing)))

    run = runner(build_input(case, root))
    if run.release is None:
        message = run.qc1.error_message or run.qc2.error_message or "no release decision"
        return CaseResult(case, error=message)
    remaining = run.qc1.issues + run.qc2.issues
    found, missed = [], []
    applicable = [e for e in case.expected.issues if e.needs is None or e.needs in evaluators_available]
    for expected in applicable:
        match = next((i for i in remaining if expected.matches(i)), None)
        if match is None:
            missed.append(expected)
        else:
            found.append(expected)
            remaining.remove(match)
    remaining = [i for i in remaining if not any(a.matches(i) for a in case.expected.acceptable)]

    return CaseResult(
        case,
        actual_decision=run.release.decision,
        found=found,
        missed=missed,
        unexpected=remaining,
        decision_checked=_ALL_RUBRIC_EVALUATORS <= evaluators_available,
    )


# ---------------------------------------------------------------------- summary


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


@dataclass(frozen=True)
class BenchmarkSummary:
    results: list[CaseResult]

    @property
    def ran(self) -> list[CaseResult]:
        return [r for r in self.results if r.ran]

    @property
    def failures(self) -> list[CaseResult]:
        return [r for r in self.ran if not r.passed]

    def metrics(self) -> dict:
        ran = [r for r in self.ran if r.scored]  # errored cases are reported, not scored
        tp = sum(len(r.found) for r in ran)
        fn = sum(len(r.missed) for r in ran)
        fp = sum(len(r.unexpected) for r in ran)
        blocking_expected = [e for r in ran for e in r.found + r.missed if e.must_block]
        blocking_found = [e for r in ran for e in r.found if e.must_block]

        per_type: dict[str, dict[str, int]] = {}
        for r in ran:
            for e in r.found:
                per_type.setdefault(e.issue_type, {"tp": 0, "fp": 0, "fn": 0})["tp"] += 1
            for e in r.missed:
                per_type.setdefault(e.issue_type, {"tp": 0, "fp": 0, "fn": 0})["fn"] += 1
            for i in r.unexpected:
                per_type.setdefault(i.issue_type, {"tp": 0, "fp": 0, "fn": 0})["fp"] += 1

        decision_checked = [r for r in ran if r.decision_checked]
        return {
            "cases_total": len(self.results),
            "cases_run": len(ran),
            "cases_skipped": len(self.results) - len(self.ran),
            "cases_errored": len(self.ran) - len(ran),
            "cases_passed": sum(r.passed for r in ran),
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "precision": _ratio(tp, tp + fp),
            "recall": _ratio(tp, tp + fn),
            "blocking_issue_recall": _ratio(len(blocking_found), len(blocking_expected)),
            "false_blocks": sum(r.actual_block and not r.expected_block for r in ran),
            "missed_blocks": sum(r.expected_block and not r.actual_block for r in ran),
            "block_accuracy": _ratio(sum(r.actual_block == r.expected_block for r in ran), len(ran)),
            "exact_decision_accuracy": _ratio(
                sum(r.actual_decision is r.case.expected.decision for r in decision_checked),
                len(decision_checked),
            ),
            "per_issue_type": dict(sorted(per_type.items())),
        }

    def to_dict(self) -> dict:
        return {
            "metrics": self.metrics(),
            "cases": [
                {
                    "case_id": r.case.case_id,
                    "title": r.case.title,
                    "status": (
                        "skipped" if not r.ran
                        else "error" if r.error
                        else "passed" if r.passed
                        else "failed"
                    ),
                    "skipped_reason": r.skipped_reason,
                    "error": r.error,
                    "expected_decision": r.case.expected.decision,
                    "actual_decision": r.actual_decision,
                    "missed": [e.label() for e in r.missed],
                    "unexpected": [f"{i.issue_id} {i.issue_type}: {i.explanation}" for i in r.unexpected],
                }
                for r in self.results
            ],
        }

    def format_report(self) -> str:
        m = self.metrics()

        def pct(value: float | None) -> str:
            return "n/a" if value is None else f"{value:.1%}"

        lines = [
            f"Benchmark: {m['cases_total']} cases | {m['cases_run']} scored | "
            f"{m['cases_skipped']} skipped | {m['cases_errored']} errored | "
            f"{m['cases_passed']}/{m['cases_run']} passed",
            f"Issues:    found {m['true_positives']} | missed {m['false_negatives']} | "
            f"false alarms {m['false_positives']}",
            f"           recall {pct(m['recall'])} | precision {pct(m['precision'])} | "
            f"blocking-issue recall {pct(m['blocking_issue_recall'])}",
            f"Blocking:  accuracy {pct(m['block_accuracy'])} | false blocks {m['false_blocks']} | "
            f"missed blocks {m['missed_blocks']}",
        ]
        if m["exact_decision_accuracy"] is None:
            lines.append(
                "Decision:  exact decisions not compared (some rubric categories need "
                "evaluators that did not run)"
            )
        else:
            lines.append(f"Decision:  exact accuracy {pct(m['exact_decision_accuracy'])}")

        for r in self.failures:
            if r.error:
                lines.append(f"\nERROR  {r.case.case_id} {r.case.title}: {r.error[:200]}")
                continue
            lines.append(f"\nFAILED {r.case.case_id} {r.case.title}")
            lines.append(f"  decision: expected {r.case.expected.decision}, got {r.actual_decision}")
            lines += [f"  missed:     {e.label()}" for e in r.missed]
            lines += [f"  unexpected: {i.issue_type} - {i.explanation}" for i in r.unexpected]

        skipped = [r for r in self.results if not r.ran]
        if skipped:
            lines.append("\nSkipped (waiting for evaluators):")
            lines += [f"  {r.case.case_id} {r.case.title} ({r.skipped_reason})" for r in skipped]
        return "\n".join(lines)


def run_benchmark(
    runner: QCRunner,
    evaluators_available: Iterable[Evaluator],
    *,
    root: Path = EVALUATION_DIR,
) -> BenchmarkSummary:
    available = frozenset(evaluators_available)
    return BenchmarkSummary([run_case(c, runner, available, root) for c in load_cases(root)])
