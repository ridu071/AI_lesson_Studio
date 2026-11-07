"""Run the QC benchmark and report how well QC finds planted problems.

Run from the backend folder:
    python scripts/run_benchmark.py                 # deterministic checks only (free, instant)
    python scripts/run_benchmark.py --llm           # full QC with the configured LLM
    python scripts/run_benchmark.py --llm --cases C-000,F-008

Writes the full result to evaluation/evaluation_results/latest[_llm].json and
exits with code 1 if any runnable case fails or errors.
"""

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import Settings, get_settings  # noqa: E402
from app.evaluation.benchmark import EVALUATION_DIR, BenchmarkSummary, load_cases, run_case  # noqa: E402
from app.llm.factory import create_llm_client  # noqa: E402
from app.modules.qc.engine import (  # noqa: E402
    DETERMINISTIC_EVALUATORS,
    FULL_EVALUATORS,
    run_deterministic_qc,
    run_full_qc,
)
from app.modules.qc.scoring.rubrics import RUBRIC_VERSION  # noqa: E402

# QC rules pinned so a local .env can never change benchmark results.
# (LLM connection settings - key, model, timeouts - still come from .env.)
PINNED = {"max_lesson_minutes": 45, "qc1_min_score": 80, "qc2_min_score": 80}
FIXED_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def make_runner(use_llm: bool):
    """Return (runner, evaluators, mode label)."""
    if use_llm:
        settings = Settings(**(get_settings().model_dump() | PINNED))
        client = create_llm_client(settings)

        def runner(qc_input):
            return run_full_qc(qc_input, client, settings=settings, now=FIXED_TIME)

        return runner, FULL_EVALUATORS, f"full ({client.model})"

    settings = Settings(_env_file=None, **PINNED)

    def runner(qc_input):
        return run_deterministic_qc(qc_input, settings=settings, now=FIXED_TIME)

    return runner, DETERMINISTIC_EVALUATORS, "deterministic (no LLM)"


def status_label(result) -> str:
    if not result.ran:
        return "skipped"
    if result.error:
        return "ERROR"
    return "pass" if result.passed else "FAIL"


def save(out: Path, results: list, mode: str, evaluators) -> None:
    # Saved after every case, so an interrupted run keeps what it learned.
    report = {
        "run_at": datetime.now(UTC).isoformat(),
        "rubric_version": RUBRIC_VERSION,
        "mode": mode,
        "evaluators": sorted(evaluators),
    } | BenchmarkSummary(results).to_dict()
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--llm", action="store_true", help="run the LLM evaluators too")
    parser.add_argument("--cases", help="comma-separated case IDs to run (default: all)")
    args = parser.parse_args()

    runner, evaluators, mode = make_runner(args.llm)
    cases = load_cases()
    if args.cases:
        wanted = {c.strip() for c in args.cases.split(",")}
        cases = [c for c in cases if c.case_id in wanted]
    out = EVALUATION_DIR / "evaluation_results" / f"latest{'_llm' if args.llm else ''}.json"

    print(f"QC benchmark - rubric {RUBRIC_VERSION} - mode: {mode}\n")
    results, started = [], time.monotonic()
    for case in cases:
        t = time.monotonic()
        result = run_case(case, runner, frozenset(evaluators))
        results.append(result)
        save(out, results, mode, evaluators)
        if args.llm:
            print(f"  {case.case_id} {status_label(result):7} {time.monotonic() - t:5.1f}s  "
                  f"{case.title}", flush=True)
        if result.error and "quota exhausted" in result.error:
            print(f"\nStopped: {result.error}\nThe remaining cases were not run.")
            break

    summary = BenchmarkSummary(results)
    print(("\n" if args.llm else "") + summary.format_report())
    print(f"\nTotal time: {time.monotonic() - started:.0f}s")
    print(f"Full results: {out}")
    return 1 if summary.failures else 0


if __name__ == "__main__":
    sys.exit(main())
