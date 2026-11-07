"""Run the QC benchmark and report how well QC finds planted problems.

Run from the backend folder:
    python scripts/run_benchmark.py

Writes the full result to evaluation/evaluation_results/latest.json and
exits with code 1 if any runnable case fails.
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import Settings  # noqa: E402
from app.evaluation.benchmark import EVALUATION_DIR, run_benchmark  # noqa: E402
from app.modules.qc.engine import DETERMINISTIC_EVALUATORS, run_deterministic_qc  # noqa: E402
from app.modules.qc.scoring.rubrics import RUBRIC_VERSION  # noqa: E402

# Pinned so a local .env or shell variable can never change benchmark results.
BENCHMARK_SETTINGS = Settings(
    _env_file=None, max_lesson_minutes=45, qc1_min_score=80, qc2_min_score=80
)
FIXED_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def main() -> int:
    summary = run_benchmark(
        lambda qc_input: run_deterministic_qc(
            qc_input, settings=BENCHMARK_SETTINGS, now=FIXED_TIME
        ),
        DETERMINISTIC_EVALUATORS,
    )
    print(f"QC benchmark - rubric {RUBRIC_VERSION} - mode: deterministic (no LLM)\n")
    print(summary.format_report())

    out = EVALUATION_DIR / "evaluation_results" / "latest.json"
    report = {
        "run_at": datetime.now(UTC).isoformat(),
        "rubric_version": RUBRIC_VERSION,
        "mode": "deterministic",
        "evaluators": sorted(DETERMINISTIC_EVALUATORS),
    } | summary.to_dict()
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nFull results: {out}")
    return 1 if summary.failures else 0


if __name__ == "__main__":
    sys.exit(main())
