# AI Lesson Studio

[![tests](https://github.com/ridu071/AI_lesson_Studio/actions/workflows/tests.yml/badge.svg)](https://github.com/ridu071/AI_lesson_Studio/actions/workflows/tests.yml)

An AI-powered lesson creation tool. From a **lesson title** and a **learning objective**
it researches websites, books and YouTube videos, writes a structured, visual lesson
that takes **45 minutes**, and checks it with **two independent quality-control (QC)
layers**. Instructors can review the audits, apply QC recommendations, edit, preview and
export. Students learn step by step and finish with a 10-question test and a review
tailored to their results.

> Built for the AI Research Intern assignment. Runs locally; deployment is not required.

---

## Quick start

Needs Python 3.11+ and two free API keys.

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # macOS/Linux: cp .env.example .env
```

Fill in `backend/.env`:

| Setting | Where to get it |
|---|---|
| `LLM_API_KEY` | Google AI Studio: aistudio.google.com, "Get API key" (Gemini) |
| `LLM_MODEL` | `gemini-3.5-flash-lite` (tested; fast) |
| `YOUTUBE_API_KEY` | Google Cloud Console: enable "YouTube Data API v3", then Credentials, Create API key (optional; without it, no videos) |

Run the app and open http://localhost:8501:

```bash
streamlit run streamlit_app.py
```

Other commands (from `backend/`):

| Command | Purpose |
|---|---|
| `pytest` | 247 offline tests (a fake LLM; no network, no keys) |
| `python scripts/check_setup.py` | Checks Python, packages, folders and settings |
| `python scripts/run_benchmark.py` | QC benchmark, deterministic checks only (free, instant) |
| `python scripts/run_benchmark.py --llm` | QC benchmark with the AI evaluators (about 52 calls) |
| `python scripts/run_repeatability.py` | Runs every case 3 times: are QC results stable? |
| `python scripts/qc_report.py --case F-001 --llm` | One lesson's full QC report |

---

## What it does (mapped to the brief)

| Requirement | How |
|---|---|
| Title + objective inputs; empty/invalid input handled | Validated before anything runs; friendly messages; duplicate topics detected |
| Research **websites** | Wikipedia articles; the most relevant paragraphs are kept **word for word** as evidence |
| Research **books** | Open Library (title, author, link): references and further reading |
| Research **YouTube** | YouTube Data API: videos with channel and length, as optional extra viewing |
| Structured, engaging content | 7 segments: Intro and goal (4 min), Overview (3), Core idea 1 (8), Core idea 2 (8), Worked example + "Try it" activity (7), Test (10), Recap (5) |
| Explanations, examples, practical application, activities, knowledge checks | Short chunks, analogies and examples; a hands-on "Try it" task with hint and answer; a check question in each core idea; a 10-question test |
| Visuals | Flowcharts, concept maps, timelines, labelled diagrams, tables, charts, formula cards, code and analogy scenes, **drawn by the app** from a structured spec |
| 45 minutes | Enforced: section minutes must add up to 40-45; QC2 blocks anything over 45 |
| Reference links at the end | Built by code from the research (never written by the AI) |
| **QC1: research and factual accuracy** | Every factual claim checked against the evidence passages; fabricated / contradicted / unsupported / misleading citations; source credibility and freshness; research gaps; internal contradictions |
| **QC2: instructional quality** | Objective coverage matrix (explained, exemplified, practised, assessed), Bloom-level alignment, structure and sequencing, clarity for the learner level, answer-key checks, hint quality |
| Separate audit reports with fixes | `qc1_factual_audit.md` and `qc2_instructional_audit.md`, each issue with location, evidence and a suggested fix |
| Review, edit, save | Teacher tools, then Edit: text, visuals, questions; every save is a new version |
| Review and apply QC recommendations | Teacher tools, then Improve: pick issues or write an instruction; the AI revises and the new version is re-checked automatically |
| Preview | The Learn view (exactly what students see), plus a preview of any earlier version and a **what changed** diff between any two versions (Teacher tools, then Version history) |
| Export | **PDF notes**, a **summary image**, and lesson / references / both QC reports as Markdown, JSON or a zip |
| Error handling | Every step is checkpointed to disk; a failed step shows why and offers **Try again** (resumes there); versions are never overwritten |

### The student experience

1. A centred form: topic, level and goal (or one of 4 example topics).
2. A loading screen where five ducks swim across a pond, one per real step:
   planning, finding sources, writing, fact check, teaching check.
3. **Learn**: one section at a time, with Previous / Next and a progress bar.
4. **Test**: 10 questions (multiple choice, scenario, order steps, match pairs,
   fill in the blank, label a diagram), a hint on each, and **no answers until every
   question is answered and submitted**.
5. **Your results**: a score per objective; below 70% opens a **review block** with a
   new visual or analogy, a different explanation and the common mix-ups. Wrong answers
   show the misconception behind them and the section to revisit.
6. **Recap** opens with a personal line ("You scored 8 out of 10. Strongest area ...").
7. **Sources** tab (websites, playable videos, books) and **Export** tab (PDF, summary image).

---

## How it works

```
title + objective
   │  validate inputs
   ▼
1 RESEARCH   AI plans key concepts and queries (it never produces URLs)
             Wikipedia (evidence, verbatim) · Open Library (books) · YouTube (videos)
             coverage check: a concept without evidence gets its own search
   ▼
2 GENERATE   AI writes the 7-segment lesson as structured JSON, using ONLY the evidence;
             every fact is recorded as a claim with its source.
             Code: renumbers IDs, repairs small slips, attaches videos and references,
             rejects drafts that break the rules (45 min, 10 test questions, hints, visuals...)
             and fills in a missing check question or "Try it" task with one small extra call
   ▼
3 QC1 + QC2  two independent audits (separate prompts and calls; neither sees the other)
             = deterministic checks + AI evaluators -> scores, issues, release decision
   ▼
4 REVIEW     instructor: audits, Improve (AI revision -> new version -> re-QC), Edit,
             history, exports  ·  student: Learn -> Test -> Results -> Recap
```

### Key technical decisions

- **Evidence before confidence.** QC1 does not ask the AI "is this true?". The AI only
  labels how each evidence passage relates to each claim (supports / partially supports
  / contradicts), and **code** decides the verdict. The AI is **not told which source a
  claim cites**, so it cannot just rubber-stamp the citation. "Supported" requires a
  quoted passage.
- **Rules beat scores.** Each layer has a weighted rubric score, but hard rules always
  win: a fabricated citation, a contradicted claim, more than 45 minutes, or an
  objective that is never assessed **blocks** the lesson, whatever its score.
- **Honest scoring.** A rubric category is scored only if every check that can find its
  issues actually ran; otherwise it shows "not evaluated" instead of a made-up number.
- **The AI never creates links.** References and videos come from the research APIs;
  the generator may only cite sources that have evidence passages (books and videos are
  metadata only, so they are never treated as evidence).
- **Repair, don't fail.** Small model slips (wrong ID format, text in the wrong field,
  more than 10 test questions, a missing hint, citing a book) are fixed in code; real
  problems (an unsourced fact, too few questions) are sent back to the model with the
  exact reason.
- **Nothing is lost.** Each step is saved the moment it succeeds; every edit or revision
  is a new version with its own QC audit, pinned to that version's content hash.
- **Safety.** Lesson and web text are treated as untrusted data in every prompt (prompt
  injection), research can only reach an allowlist of HTTPS API hosts (SSRF), and user
  or model text is escaped before it is shown in the page.
- **Stack.** Python 3.12, Pydantic (data contracts), Gemini via REST behind a
  provider-neutral interface, Streamlit (UI, Graphviz diagrams), ReportLab (PDF),
  Pillow (summary image), JSON files for storage. Simple choices for a local tool; the
  QC design is documented in `docs/qc_specification.md`.

---

## Results

### Demo lessons (`demo/`)

| | HTTP Requests and Responses (sample) | Photosynthesis (own choice) |
|---|---|---|
| Research | Wikipedia *HTTP*, *List of HTTP status codes*; 3 books; 3 videos | Wikipedia *Photosynthesis*, *Chlorophyll*, *Photosystem*; 3 books; 3 videos |
| Lesson | 7 segments, 45 min, 10 visuals, 2 checks, "Try it", 10-question test | same |
| QC | QC1 100, QC2 100: eligible for instructor review | v1 and v2 both 100 |
| Manual fact check | All claims and answer keys correct | All correct, **but** two questions used "primary electron donor" for different things; neither QC layer caught it. Fixed via Improve with an instructor instruction (v2) |

Details, and both versions' QC reports, are in [`demo/README.md`](demo/README.md).

### QC accuracy benchmark

27 lessons with deliberately planted problems (fabricated citations, contradicted
facts, 60-minute lessons, untested objectives, wrong answer keys, jargon for beginners,
...) and control cases that must **not** be flagged. See [`evaluation/`](evaluation/).

Latest run (2026-11-07, current prompts: QC1 0.1.0, QC2 0.3.0, `gemini-3.5-flash-lite`):

| Mode | Cases scored | Passed | Recall | Precision | Block accuracy | Exact decisions |
|---|---|---|---|---|---|---|
| Deterministic checks only | 21 (6 need the AI) | 21 | 100% | 100% | 100% | n/a |
| Full (with AI evaluators) | 23 of 26 (run before I-015 was added) | **23** | **100%** (25/25) | **100%** | **100%** | **100%** |

The free-tier daily quota ran out after 23 cases. The 3 that did not run (I-012 to
I-014) passed in the previous full run (25/26, earlier QC2 prompt), whose one false
alarm (F-009) is fixed in the current prompt.

I-015 (added after the demo) plants the kind of error QC missed in the Photosynthesis
lesson: two final questions asking the same thing with opposite answer keys. It has not
been run with the AI evaluators yet (quota), so it is an open test, not a claimed pass.

Repeatability (3 runs × 26 cases, earlier prompt versions): 100% identical decisions,
96.2% identical issue sets.

> Caveat: the checks and the benchmark cases were written by the same author, on one
> topic. These numbers show the engine does what it was designed to do; confidence on
> real lessons needs cases written by instructors.

---

## Known limitations

1. **QC1 verifies the claims the generator records.** A factual sentence that was not
   recorded as a claim is not checked against evidence. (An independent claim extractor
   is designed in `docs/qc_specification.md` but not built.)
2. **QC is good, not perfect.** The demo shows a confusing pair of test questions that
   both layers passed; the instructor review step exists for exactly this.
3. **The lite model writes tersely**: about 450-500 words per lesson instead of the
   1,200-1,500 the prompt asks for, so the visuals carry more of the teaching. A larger
   model would follow the specification more closely (one line in `.env`).
4. **Evidence comes only from Wikipedia.** It is a solid tertiary source for
   introductory topics, but not for specialist or very recent ones. Books and videos are
   listed but not read.
5. **The PDF shows diagrams as tables and arrow lists**, because graph drawing happens
   in the browser.
6. **Free-tier API keys**: rate limits apply, and the provider may use free-tier prompts
   for training, so do not send real student data.

---

## Project layout

```
backend/
  streamlit_app.py       the app (student pages + teacher tools)
  app/workflow.py        steps, checkpoints, retry, versions, export
  app/research/          Wikipedia, Open Library, YouTube; allowlisted HTTP
  app/generation/        generation, revision, completion, visuals, grading, PDF/image export
  app/modules/qc/        QC1, QC2, rubrics and scoring, decision rules, reports
  app/llm/               Gemini client (retries, quota handling, structured JSON output)
  app/schemas/           lesson and research data contracts
  tests/                 247 unit tests
prompts/                 versioned prompts (research, generation, qc1, qc2)
evaluation/              QC benchmark: base lesson + 27 cases
demo/                    exported demo lessons, PDFs, summary images, QC reports
docs/                    QC specification, demo video script
```

---

## Acknowledgements

**Data sources and services**
- **Wikipedia** (via the MediaWiki API): evidence passages are quoted from Wikipedia
  articles, which are licensed under CC BY-SA 4.0; every lesson links back to the
  articles it uses.
- **Open Library** (Internet Archive) search API: book suggestions.
- **YouTube Data API v3** (Google): video search and metadata.
- **Google Gemini** (`gemini-3.5-flash-lite`): research planning, lesson generation
  and the AI parts of both QC layers.

**Open-source libraries**: Streamlit, Pydantic and pydantic-settings, ReportLab, Pillow,
pandas, pytest (and pypdf in one optional test). Diagrams are rendered by Streamlit's
built-in Graphviz support.

**AI assistance**: this project was built with the help of an AI coding assistant
(Claude Code by Anthropic), used for writing and debugging code, tests and
documentation, as the brief allows. The architecture, design decisions and
trade-offs were reviewed and directed by me, and I can explain every part of the
implementation.

The lesson content in `demo/` was generated by the tool itself and fact-checked by hand
as described in `demo/README.md`.
