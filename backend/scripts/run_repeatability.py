"""Run every benchmark case several times with the LLM and measure stability.

Run from the backend folder:
    python scripts/run_repeatability.py              # 3 runs per case
    python scripts/run_repeatability.py --runs 5 --cases C-000,F-009

Uses about (cases x runs x 2) LLM calls. Writes
evaluation/evaluation_results/repeatability.json.
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import Settings, get_settings  # noqa: E402
from app.evaluation.benchmark import EVALUATION_DIR, load_cases  # noqa: E402
from app.evaluation.repeatability import measure  # noqa: E402
from app.llm.factory import create_llm_client  # noqa: E402
from app.modules.qc.engine import run_full_qc  # noqa: E402

PINNED = {"max_lesson_minutes": 45, "qc1_min_score": 80, "qc2_min_score": 80}
FIXED_TIME = datetime(2026, 11, 7, tzinfo=UTC)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--cases", help="comma-separated case IDs (default: all)")
    args = parser.parse_args()

    settings = Settings(**(get_settings().model_dump() | PINNED))
    client = create_llm_client(settings)
    cases = load_cases()
    if args.cases:
        wanted = {c.strip() for c in args.cases.split(",")}
        cases = [c for c in cases if c.case_id in wanted]

    print(f"Repeatability - {client.model} - {args.runs} runs x {len(cases)} cases\n", flush=True)
    def progress(c) -> None:
        state = "stable" if c.decision_stable and c.issues_stable else "VARIES"
        errors = f", {c.errors} errored" if c.errors else ""
        print(f"  {c.case_id} {state}{errors}  {c.title}", flush=True)

    summary = measure(
        cases, lambda qi: run_full_qc(qi, client, settings=settings, now=FIXED_TIME), args.runs,
        on_case=progress,
    )
    print()
    print(summary.format_report())

    out = EVALUATION_DIR / "evaluation_results" / "repeatability.json"
    report = {"run_at": datetime.now(UTC).isoformat(), "model": client.model,
              "runs_per_case": args.runs} | summary.to_dict()
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nFull results: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
