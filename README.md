# AI Lesson Studio

An AI-powered lesson creation tool. From a **lesson title** and a **learning
objective** it researches websites, books and YouTube videos, writes a
structured lesson that takes at most 45 minutes, and checks it with **two
independent QC layers**. An instructor can then review, edit, apply QC
recommendations, preview and export the lesson.

## Run it

Windows, Python 3.11+. From `backend/`:

```
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # then set LLM_API_KEY (Gemini) and YOUTUBE_API_KEY
streamlit run streamlit_app.py
```

Open http://localhost:8501, then enter a title and objective and press **Research and generate**.

Other commands (from `backend/`):

| Command | Purpose |
|---|---|
| `pytest` | 223 offline tests (a fake LLM; no network) |
| `python scripts/run_benchmark.py --llm` | QC accuracy on 26 benchmark cases with planted errors |
| `python scripts/run_repeatability.py` | Do repeated QC runs give the same results? |

## The flow

```
Title + objective ──► validate inputs
   │
   ▼
1. RESEARCH   LLM plans key concepts and queries (it never produces URLs)
              ├─ Wikipedia   full articles; relevant paragraphs kept WORD FOR WORD as evidence
              ├─ Open Library books (metadata only: references / further reading)
              └─ YouTube     videos + durations (metadata only: supplementary)
              coverage check: a key concept with no evidence gets its own search
   │
   ▼
2. GENERATE   LLM writes the structured lesson from the evidence only; every fact
              is recorded as a claim citing its source. Code attaches videos and
              builds the reference list, so no link can be invented.
              Draft rejected and retried if: >45 or <40 min, cites non-evidence, too thin.
   │
   ▼
3. QC         QC1 factual accuracy  ┐ independent: separate prompts and calls;
              QC2 instructional     ┘ neither sees the other's results
              ──► two separate audit reports + a release decision
   │
   ▼
4. REVIEW     preview · edit and save · apply QC recommendations (AI revision,
              then automatic re-QC) · dismiss issues · version history · export
```

## How each requirement is met

| Requirement | Where |
|---|---|
| Title and objective inputs, empty or invalid input rejected | `app/workflow.py` `validate_inputs` |
| Research books, websites, YouTube | `app/research/` (Open Library, Wikipedia, YouTube Data API) |
| Explanations, examples, practical application, knowledge checks | 7-segment visual lesson (intro 4, overview 3, two core ideas 8+8, worked example 7, practice and test 10, recap 5 min) with check questions, 3 practice tasks with hints, a 5-question quiz and visuals drawn by the app (flowcharts, concept maps, tables, timelines, charts, formula cards, code, analogy scenes): `prompts/generation/lesson.md`, `app/generation/` |
| YouTube videos as supplementary resources | Attached by code from research; optional, not counted in the 45 minutes |
| Reference links at the end | Built by code from research (`app/generation/render.py`) |
| 45-minute limit | The generator rejects drafts outside 40-45 min; QC2 enforces it as a hard rule |
| QC1: factual correctness, unsupported or misleading claims, source reliability, gaps, inconsistencies | `app/modules/qc/qc1/` |
| QC2: objective alignment, clarity, structure, gaps in explanations, examples and practice | `app/modules/qc/qc2/` |
| Separate audit reports with issues and suggested fixes | `qc1_factual_audit.md`, `qc2_instructional_audit.md` |
| Review, edit, save | App tab **Edit**: each save is a new version |
| Review and apply QC recommendations | Tab **Apply recommendations**: AI revision → new version → re-QC |
| Preview | Tab **Preview** |
| Export lesson, references, QC reports | Tab **Export**: Markdown, JSON or one zip |
| AI and research failures, preserved work, retry | Every step checkpointed to disk; a failed step shows its error and a **Retry** button |

## Key technical decisions

- **Evidence before confidence.** QC1 does not ask the LLM "is this true?".
  For each claim, the LLM labels how each evidence passage relates to it
  (supports, partially supports, contradicts), and **code** decides the
  verdict. The model is not told which source a claim cites, so it can't just
  rubber-stamp the citation. "Supported" requires a quoted passage.
- **Rules beat scores.** Each layer scores a weighted rubric, but hard rules
  always win. A fabricated citation, a contradicted claim, more than 45 minutes,
  or an objective that is never assessed **blocks** the lesson, whatever the score.
- **The LLM never creates links.** Videos and references come from the
  research APIs, and the generator can cite only sources that have evidence
  passages.
- **Books and videos are metadata only.** A title doesn't prove content, so
  they are references and supplementary material, never evidence.
- **Untrusted content.** All prompts treat lesson and web text as data, not
  instructions. Research can reach only an allowlist of HTTPS API hosts.
- **Nothing is overwritten.** Every revision or edit is a new version with
  its own QC audit, which is pinned to that version's content hash.
- **Stack:** Python, Pydantic contracts, Gemini (`gemini-3.5-flash-lite`) via
  REST behind a provider-neutral interface, Streamlit for the UI, and plain
  JSON files for storage (`data/projects/`). These are simple choices for a
  local tool; the design rules are in `docs/qc_specification.md`.

## Demo results (2026-11-07)

Exported lessons, references and both QC reports are in [`demo/`](demo/).

| | HTTP Requests and Responses (sample) | Photosynthesis (own choice) |
|---|---|---|
| Research | Wikipedia *HTTP* (17 passages), *List of HTTP status codes* (11); 3 books; 3 videos | *Photosynthesis* (19), *Chlorophyll* (5), *Photosystem* (4); 3 books; 3 videos |
| v1 QC | QC1 100, QC2 100, eligible | QC1 100, QC2 95.5. QC2 found 3 issues: beginner-unfriendly jargon (x2) and a missing summary |
| Revision | Instructor note: explain POST properly and add the activity's sample data → v2, both QC pass | Applied all 3 QC recommendations → v2: jargon removed, summary added, QC2 100 |
| Duration | 42 min | 42 min |

**Factual verification.** Each claim QC1 marked "supported" was checked by
hand against its evidence passage: 14 claims, plus all answer keys. All were
correct; most claims are near-verbatim from the passage. One mild
generalisation: "standard response for successful requests is 2xx" is
backed by the passage on 200 OK, which is a 2xx code.

**QC accuracy benchmark** (26 cases with deliberately planted problems, see
`evaluation/`): 100% of problems found, 96.7% precision, 100% correct
block/no-block decisions. Over 3 repeated runs, 100% of decisions were identical.

## Known limitations (honest)

1. **QC1 verifies the claims the generator records.** A factual sentence the
   generator did not record as a claim is not checked. Seen in the HTTP v2
   revision: a correct sentence about POST was added without a claim. The fix
   is an independent claim extractor (designed, not built).
2. **QC2 on a lite model can miss issues.** It passed an activity that
   referred to sample logs without providing them; the instructor caught it
   in review. It sometimes also labels a false statement "unclear" (a
   duplicate of QC1's finding; the decision is unaffected).
3. **Research depth.** Wikipedia is the only evidence source. It is a solid
   tertiary reference for introductory topics, but not for specialist or
   very recent topics. Books and videos are not read.
4. **Free-tier LLM key.** Rate limits apply, and free-tier prompts may be used
   for training by the provider, so use synthetic topics only.

## Layout

```
backend/
  streamlit_app.py     the instructor app
  app/workflow.py      steps, checkpoints, retry, versions, export
  app/research/        Wikipedia, Open Library, YouTube; allowlisted HTTP
  app/generation/      lesson generation, AI revision, Markdown rendering
  app/modules/qc/      QC1, QC2, scoring, decision rules, reports
  app/llm/             Gemini client (retries, structured JSON output)
prompts/               versioned prompts (research, generation, qc1, qc2)
evaluation/            QC benchmark cases
demo/                  exported demo lessons and QC reports
docs/                  QC specification
```
