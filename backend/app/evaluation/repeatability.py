"""Repeatability check (workflow section 20.2).

"The same lesson should not receive wildly different evaluations merely
because the model was called again."

Each case is run N times. An issue is identified by its layer, type and
location (issue IDs are just numbering). We report:
- decision stability: did every run reach the same release decision?
- issue stability:    did every run report the same set of issues?
- flaky issues:       issues reported in some runs but not others.
Errored runs (LLM down) are counted separately and not compared.
"""

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from app.evaluation.benchmark import BenchmarkCase, QCRunner, build_input
from app.modules.qc.enums import ReleaseDecision
from app.modules.qc.schemas import QCIssue

Signature = tuple[str, str, str]


def signature(issue: QCIssue) -> Signature:
    where = issue.claim_id or issue.objective_id or issue.section_id or "lesson"
    return (issue.audit_type.value, issue.issue_type.value, where)


@dataclass(frozen=True)
class CaseStability:
    case_id: str
    title: str
    runs: int
    errors: int
    decisions: tuple[ReleaseDecision, ...]  # from successful runs only
    issue_counts: dict[Signature, int]  # in how many successful runs each issue appeared
    error_messages: tuple[str, ...] = ()

    @property
    def successful(self) -> int:
        return self.runs - self.errors

    @property
    def decision_stable(self) -> bool:
        return self.successful > 0 and len(set(self.decisions)) == 1

    @property
    def flaky_issues(self) -> list[tuple[Signature, int]]:
        return sorted((s, n) for s, n in self.issue_counts.items() if n < self.successful)

    @property
    def issues_stable(self) -> bool:
        return self.successful > 0 and not self.flaky_issues


def measure_case(case: BenchmarkCase, runner: QCRunner, runs: int) -> CaseStability:
    qc_input = build_input(case)
    decisions: list[ReleaseDecision] = []
    counts: Counter[Signature] = Counter()
    errors: list[str] = []
    for _ in range(runs):
        result = runner(qc_input)
        if result.release is None:
            errors.append(result.qc1.error_message or result.qc2.error_message or "no decision")
            continue
        decisions.append(result.release.decision)
        counts.update({signature(i) for i in result.qc1.issues + result.qc2.issues})
    return CaseStability(case.case_id, case.title, runs, len(errors), tuple(decisions),
                         dict(counts), tuple(errors))


@dataclass(frozen=True)
class StabilitySummary:
    cases: list[CaseStability]

    def metrics(self) -> dict:
        compared = [c for c in self.cases if c.successful >= 2]
        def rate(values: list[bool]) -> float | None:
            return round(sum(values) / len(values), 4) if values else None
        return {
            "cases": len(self.cases),
            "cases_compared": len(compared),
            "errored_runs": sum(c.errors for c in self.cases),
            "decision_stability": rate([c.decision_stable for c in compared]),
            "issue_set_stability": rate([c.issues_stable for c in compared]),
            "flaky_issue_count": sum(len(c.flaky_issues) for c in compared),
        }

    def to_dict(self) -> dict:
        return {
            "metrics": self.metrics(),
            "cases": [
                {
                    "case_id": c.case_id,
                    "runs": c.runs,
                    "errors": c.errors,
                    "error_messages": list(c.error_messages),
                    "decisions": list(c.decisions),
                    "decision_stable": c.decision_stable,
                    "flaky_issues": [{"issue": "/".join(s), "seen_in_runs": n} for s, n in c.flaky_issues],
                }
                for c in self.cases
            ],
        }

    def format_report(self) -> str:
        m = self.metrics()
        def pct(v: float | None) -> str:
            return "n/a" if v is None else f"{v:.1%}"
        lines = [
            f"Repeatability: {m['cases']} cases, {m['cases_compared']} compared, "
            f"{m['errored_runs']} errored runs",
            f"  Same decision every run:   {pct(m['decision_stability'])}",
            f"  Same issues every run:     {pct(m['issue_set_stability'])}",
            f"  Flaky issues:              {m['flaky_issue_count']}",
        ]
        for c in self.cases:
            if c.successful >= 2 and not (c.decision_stable and c.issues_stable):
                lines.append(f"\n{c.case_id} {c.title}")
                if not c.decision_stable:
                    lines.append(f"  decisions differ: {', '.join(c.decisions)}")
                for s, n in c.flaky_issues:
                    lines.append(f"  flaky: {'/'.join(s)} (in {n} of {c.successful} runs)")
        return "\n".join(lines)


def measure(
    cases: Iterable[BenchmarkCase],
    runner: QCRunner,
    runs: int,
    on_case: Callable[[CaseStability], None] | None = None,
) -> StabilitySummary:
    if runs < 2:
        raise ValueError("repeatability needs at least 2 runs per case")
    results = []
    for case in cases:
        result = measure_case(case, runner, runs)
        results.append(result)
        if on_case:
            on_case(result)
    return StabilitySummary(results)
