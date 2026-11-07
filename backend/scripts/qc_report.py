"""Run QC on a lesson and write the instructor's report.

Run from the backend folder:
    python scripts/qc_report.py --case F-001            # a benchmark case
    python scripts/qc_report.py --case F-001 --llm      # with the LLM evaluators
    python scripts/qc_report.py --lesson L.json --research R.json --objective "..."

Writes Markdown (report) and JSON (audits) to evaluation/evaluation_results/reports/.
"""

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings  # noqa: E402
from app.evaluation.benchmark import EVALUATION_DIR, build_input, load_cases  # noqa: E402
from app.llm.factory import create_llm_client  # noqa: E402
from app.modules.qc.engine import run_deterministic_qc, run_full_qc  # noqa: E402
from app.modules.qc.reporting import render_markdown  # noqa: E402
from app.modules.qc.schemas import QCInput  # noqa: E402


def load_input(args) -> tuple[QCInput, str]:
    if args.case:
        case = next((c for c in load_cases() if c.case_id == args.case), None)
        if case is None:
            sys.exit(f"Unknown case {args.case}")
        return build_input(case), args.case
    if not (args.lesson and args.research and args.objective):
        sys.exit("Give --case, or all of --lesson, --research and --objective")
    lesson = json.loads(Path(args.lesson).read_text(encoding="utf-8"))
    research = json.loads(Path(args.research).read_text(encoding="utf-8"))
    qc_input = QCInput(request_objective=args.objective, lesson=lesson, research=research)
    return qc_input, f"{qc_input.lesson.lesson_id}-v{qc_input.lesson.version}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case")
    parser.add_argument("--lesson")
    parser.add_argument("--research")
    parser.add_argument("--objective")
    parser.add_argument("--llm", action="store_true", help="run the LLM evaluators too")
    args = parser.parse_args()

    qc_input, name = load_input(args)
    if args.llm:
        settings = get_settings()
        run = run_full_qc(qc_input, create_llm_client(settings), settings=settings)
    else:
        run = run_deterministic_qc(qc_input)

    out_dir = EVALUATION_DIR / "evaluation_results" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = out_dir / f"{name}.md"
    report.write_text(render_markdown(qc_input, run), encoding="utf-8")
    audits = {
        "qc1": run.qc1.model_dump(mode="json"),
        "qc2": run.qc2.model_dump(mode="json"),
        "release": run.release.model_dump(mode="json") if run.release else None,
    }
    (out_dir / f"{name}.json").write_text(json.dumps(audits, indent=2), encoding="utf-8")
    print(f"Decision: {run.release.decision if run.release else 'none (an audit errored)'}")
    print(f"Report:   {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
