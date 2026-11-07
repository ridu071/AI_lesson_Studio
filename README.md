# AI Lesson Studio

An AI-powered lesson creation and quality-assurance platform: research, generate,
validate, teach. Every lesson passes two independent QC layers before an
instructor approves it.

- **QC1 - factual accuracy:** every claim is checked against research evidence.
- **QC2 - instructional quality:** does the lesson actually teach its objectives in 45 minutes?

**Status:** Milestone 1, the QC engine, is complete. Research, generation, the
instructor dashboard and the student site come next. The design rules are in
[docs/qc_specification.md](docs/qc_specification.md).

## Setup (Windows, Python 3.11+)

```
cd backend
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env        # then put your LLM key in .env (never commit it)
python scripts/check_setup.py
```

## Commands (from `backend/`)

| Command | What it does | LLM calls |
|---|---|---|
| `pytest` | All unit tests (offline, uses a fake LLM) | none |
| `python scripts/run_benchmark.py` | Benchmark, deterministic checks only | none |
| `python scripts/run_benchmark.py --llm` | Benchmark with the LLM evaluators | ~2 per case |
| `python scripts/run_repeatability.py --runs 3` | Same cases several times: are results stable? | ~6 per case |
| `python scripts/qc_report.py --case F-001 --llm` | Instructor QC report for one lesson | 2 |

Reports and results are written to `evaluation/evaluation_results/` (not committed).

## Layout

```
backend/app/
  core/          settings
  schemas/       lesson and research data contracts
  modules/qc/    the QC engine: qc1/, qc2/, scoring/, validation/, engine.py, reporting.py
  llm/           provider-neutral LLM client (Gemini today)
  evaluation/    benchmark and repeatability
prompts/         versioned LLM prompts (qc1/, qc2/)
evaluation/      benchmark lessons and cases (see evaluation/README.md)
docs/            specifications
```

## Privacy note

A free-tier LLM key may allow the provider to use prompts for training. Use
only synthetic data, like the benchmark, with such a key. Never send real
student data through it.
