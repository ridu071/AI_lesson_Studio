# QC Engine Specification

Status: **Milestone 1 complete (QC engine).** Rubric version `0.1.0`
(defined in `scoring/rubrics.py`, next to the weights it describes).

This document defines what the QC engine receives, what it produces, and the
rules that decide whether a lesson may go to the instructor. The code is the
source of truth for field-level detail; this document explains the *why*.

| Contract | Code |
|---|---|
| Lesson document | [`backend/app/schemas/lesson.py`](../backend/app/schemas/lesson.py) |
| Research package | [`backend/app/schemas/research.py`](../backend/app/schemas/research.py) |
| QC input, issues, audits, release result | [`backend/app/modules/qc/schemas.py`](../backend/app/modules/qc/schemas.py) |
| QC vocabulary (statuses, severities, issue types) | [`backend/app/modules/qc/enums.py`](../backend/app/modules/qc/enums.py) |
| Default severity and hard gate per issue type | [`backend/app/modules/qc/policy.py`](../backend/app/modules/qc/policy.py) |
| QC1 deterministic checks | [`backend/app/modules/qc/qc1/`](../backend/app/modules/qc/qc1/) |
| QC2 deterministic checks | [`backend/app/modules/qc/qc2/`](../backend/app/modules/qc/qc2/) |
| Rubrics, weights, penalties | [`backend/app/modules/qc/scoring/`](../backend/app/modules/qc/scoring/) |
| Audit outcome and release decision | [`backend/app/modules/qc/validation/decision.py`](../backend/app/modules/qc/validation/decision.py) |
| End-to-end run | [`backend/app/modules/qc/engine.py`](../backend/app/modules/qc/engine.py) |

## 1. Data flow

```
QCInput = request_objective + LessonVersion (frozen) + ResearchPackage
              │
     ┌────────┴────────┐        both layers read the same snapshot, in parallel
     ▼                 ▼
 QC1 AuditReport   QC2 AuditReport   each pinned to lesson_id + version + content_hash
     └────────┬────────┘
              ▼
       ReleaseResult                 eligible / revision_required / manual_review / blocked
```

## 2. Contracts at a glance

- **LessonVersion** holds objectives (with Bloom level), sections (with type and
  minutes), claims, activities, assessment questions and videos. Every item has
  a typed ID (`LO-01`, `SEC-03`, `CL-004`, `SRC-002`, …).
- **ResearchPackage** holds sources with their evidence passages, plus honest
  `limitations`. Each source records `content_access` (full text, excerpt, or
  metadata only), because a title is not proof of content.
- **AuditReport**: one per layer. It holds the status, the weighted score with
  its subscores, the evaluators that actually ran, issues, QC1 claim verdicts
  and the QC2 objective coverage matrix.
- **QCIssue** holds the type, severity, the `hard_gate` flag, the
  `requires_manual_review` flag (the engine cannot decide this alone), an
  explanation, the location (section, claim, objective), evidence references
  and a recommendation.
- **ReleaseResult**: the combined decision, with reasons and the IDs of the
  issues that block release.

All contracts reject unknown fields and are immutable once created.

## 3. Structure vs quality: who rejects what

| Problem | Caught by | Result |
|---|---|---|
| Wrong shape, missing required field, bad ID format | Schema | Rejected, goes to *structural repair* |
| Duplicate IDs, reference to a section or objective not in the lesson | Schema | Rejected, goes to *structural repair* |
| Lesson over 45 minutes, stated time ≠ real time | QC2 | Issue |
| Citation to a source not in the research package | QC1 | Issue (`fabricated_citation`) |
| Objective never assessed | QC2 | Issue (`objective_not_assessed`) |

Rule: **the schema rejects lessons it cannot read. QC reports lessons it can
read but that are wrong.** A quality problem must never crash QC.

## 4. Audit statuses

| Status | Meaning |
|---|---|
| `pending`, `running` | In progress |
| `passed` | Finished. Only medium/low issues remain |
| `needs_revision` | Finished. Fixable problems found |
| `manual_review` | Finished. A human must judge (e.g. key evidence inaccessible) |
| `blocked` | Finished. A hard gate or critical issue was found |
| `error` | **Could not finish** (e.g. model timeout). Not a judgement of the lesson. Retry |
| `stale` | The lesson changed after this audit ran |

There is deliberately no `failed`: it could mean either "the lesson failed" or
"the audit crashed", and those need opposite responses.

## 5. Release decision rule

Each layer's audit outcome is decided by these rules, in order. The first
rule that matches wins.

| # | Condition (within one layer) | Audit outcome |
|---|---|---|
| 1 | Any issue is `critical` or a hard gate | `blocked` |
| 2 | Any issue has `requires_manual_review`, or any rubric category is not evaluated | `manual_review` |
| 3 | Any `high` issue, or the score is below the layer threshold (80) | `needs_revision` |
| 4 | Otherwise | `passed` |

The release decision is the **worse** of the two outcomes:
`blocked` → **blocked**, `manual_review` → **manual_review**,
`needs_revision` → **revision_required**, `passed` → **eligible_for_instructor_review**.

- `medium` and `low` issues never block. They appear as recommendations.
- An `error`, `pending`, `running` or `stale` audit produces **no decision**: rerun it first.
- An audit whose lesson ID, version or content hash differs from the lesson
  being decided is rejected (E2E-009, E2E-016).
- "Eligible" is not "approved". Only the instructor approves (workflow §9.6).

These rules are also enforced by the contracts themselves:

- A `passed` audit cannot contain a high, critical, hard-gate or manual-review issue.
- An `eligible` release cannot list blocking issues.
- A `blocked` release must list them.
- A claim verdict of `supported`, `partially_supported` or `contradicted` must
  cite an evidence passage ("evidence before confidence").
- The score must equal the weighted subscores, and the weights must sum to 1.
- An audit is `blocked` if and only if it contains a blocking issue.
- A `passed` audit must have every rubric category evaluated.
- While any category is not evaluated, the layer score is empty, never partial.

## 5a. Scoring

Weights are the workflow's starting values (§7.2, §7.3), to be calibrated in Step 5.

- Each category starts at 100 and loses points for each issue in it:
  critical −50, high −25, medium −10, low −3, never below 0.
- Layer score = Σ weight × category score.
- **A category is evaluated only when every evaluator that can find its issues
  has run.** Otherwise "no issues found" would only mean "not checked", and
  the category score is empty.
- Each issue type is scored in exactly one category of its own layer (tested).

| QC1 category | Weight | Needs | QC2 category | Weight | Needs |
|---|---|---|---|---|---|
| claim_evidence_support | 0.30 | citation check + claim verification | objective_alignment | 0.25 | coverage + assessment check + instructional review |
| source_credibility | 0.20 | source assessment | clarity | 0.15 | instructional review |
| citation_integrity | 0.15 | citation check + claim verification | learning_progression | 0.15 | structure check + instructional review |
| cross_source_consistency | 0.15 | consistency check | examples | 0.10 | coverage + instructional review |
| factual_correctness | 0.15 | claim verification | activities | 0.10 | coverage + instructional review |
| research_coverage | 0.05 | gap detection | assessment_effectiveness | 0.15 | assessment check + instructional review |
| | | | engagement_accessibility | 0.05 | instructional review |
| | | | time_feasibility | 0.05 | duration check |

**Consequence until Step 6:** only `time_feasibility` can be evaluated without
an LLM. So with deterministic checks alone, a lesson can be `blocked` (hard
gates and critical issues work fully), but its best possible outcome is
`manual_review`. It can never be `eligible`. This is intended: the engine does
not claim to have checked what it has not.

## 6. Issue catalogue

Each type belongs to exactly one layer, so QC1 and QC2 stay independent.
Severities are starting values, to be calibrated against the benchmark in
Step 5. The code table is `policy.py`, and a test keeps it identical to this one.

A check may **raise** an issue's severity (e.g. a missing citation on a key
claim) but can never lower it or switch a hard gate off.

"Detected by": **det** = deterministic check (Step 3), **LLM** = language
model evaluator (Step 6).

### QC1: factual accuracy

| Issue type | Severity | Hard gate | Detected by |
|---|---|---|---|
| `fabricated_citation` (cited source not in research package) | critical | yes | det |
| `contradicted_claim` | critical | yes | LLM |
| `unsupported_claim` | high | | LLM |
| `misleading_citation` (source exists but does not say this) | high | | LLM |
| `internal_contradiction` | high | | LLM |
| `partially_supported_claim` | medium | | LLM |
| `missing_citation` (factual/definition claim cites nothing) | medium | | det |
| `unverifiable_claim` (only unreadable sources cited, needs manual review) | medium | | det, LLM |
| `inaccessible_source` | medium | | det |
| `low_credibility_source` (community or unknown authority) | medium | | det |
| `research_gap` | medium | | LLM |
| `outdated_source` (judged per topic) | low | | LLM |

### QC2: instructional quality

| Issue type | Severity | Hard gate | Detected by |
|---|---|---|---|
| `duration_exceeded` (mandatory content > 45 min) | high | yes | det |
| `objective_not_assessed` (no final question) | high | yes | det |
| `incorrect_answer_key` | high | | det, LLM |
| `objective_not_explained` | high | | det |
| `bloom_mismatch` (final questions below the objective's level) | high | | det, LLM |
| `missing_section` | medium | | det |
| `objective_not_exemplified` | medium | | det |
| `objective_not_practiced` | medium | | det |
| `duration_mismatch` (stated ≠ real; activities exceed their section) | medium | | det |
| `poor_sequencing` | medium | | det, LLM |
| `unclear_explanation` | medium | | LLM |
| `weak_assessment` | medium | | det, LLM |
| `weak_example` | low | | LLM |
| `unclear_activity` | low | | LLM |
| `accessibility_issue` | low | | LLM |

## 6a. Deterministic check rules

These run without an LLM, so they are fast, free and always give the same result.

**QC1 citations**
- Every source ID cited by a section, claim or video must exist in the research
  package, otherwise `fabricated_citation`.
- `factual` and `definition` claims must cite at least one source, otherwise
  `missing_citation`. Mathematical claims are checked by computation instead.
  Opinions, hypothetical examples, instructions and exercises need no source.
- A cited source marked `inaccessible` gives `inaccessible_source`, once per source.
- A claim whose real cited sources include none with readable evidence
  (passages present and not inaccessible) gives `unverifiable_claim` with
  manual review. A claim that cites only fabricated IDs is not reported twice.

**QC2 structure**
- Required sections: introduction, concept_explanation, final_assessment, summary.
- The introduction must be first.
- An objective must be explained (concept_explanation) before any worked
  examples, practical application, knowledge check or final assessment use it.

**QC2 coverage matrix** (per objective; uses the lesson's declared mappings)
- explained: a concept_explanation section maps to it.
- exemplified: a worked_examples section, or a section with an example block, maps to it.
- practiced: a **mandatory** activity maps to it.
- assessed: a **final** assessment question maps to it. Knowledge checks alone do not count.

**QC2 assessments**
- Bloom: the highest-level final question for an objective must reach the
  objective's Bloom level. Higher is fine.
- Multiple choice: at least 2 distinct options, and the answer key must be one of them.
- True/false: options exactly True/False, and the answer key True or False.
- Answers are compared ignoring case and extra spaces.

## 6b. LLM evaluator rules

Code: `qc1/llm_review.py`, `qc2/llm_review.py`, `app/llm/`. Prompts:
`prompts/qc1/llm_review.md`, `prompts/qc2/llm_review.md` (versioned; the version
and model are stored in every audit).

**General**
- One call per layer per lesson, temperature 0, output constrained to a JSON
  schema. The answer is validated for shape **and** meaning (every claim
  answered, no invented IDs). One retry with the rejection reason. If it is
  still invalid, or the provider is down after retries, the audit is `error`:
  no decision until it is rerun. It never counts against the lesson.
- Lesson and research content is passed as untrusted data. The prompts tell
  the model never to follow instructions found inside it (workflow §16.2).
- Severity always comes from `policy.py`, never from the model.
- QC1 and QC2 are separate calls with separate prompts. Neither sees the other's results.

**QC1: claims.** The model only labels how each evidence passage relates to each
claim (`supports`, `partially_supports`, `contradicts`). Code decides the verdict:

| Relations found | Verdict / issue |
|---|---|
| Any passage contradicts the claim | `contradicted_claim` (critical, blocks) |
| A passage from a **cited** source supports it | supported, no issue |
| A cited passage only partially supports it | `partially_supported_claim` |
| Only passages from **uncited** sources support it | `misleading_citation` (or nothing, if `missing_citation` was already reported) |
| No passage supports it | `unsupported_claim` |

- The model is **not told which sources a claim cites**, so it cannot simply
  confirm the citation it is meant to check.
- Claims already settled by the citation check (fabricated or unverifiable
  citations) are not sent.
- The same call also reports `internal_contradictions`, `research_gaps` and
  `outdated_sources` (freshness depends on the topic).

**QC2: instructional review.** The model may report only: unclear_explanation,
weak_example, unclear_activity, weak_assessment, incorrect_answer_key,
bloom_mismatch, poor_sequencing, objective_not_explained, accessibility_issue.
Each issue must point to a real section, question or objective. An issue already
found by a deterministic check at the same place is not reported twice. The
prompt asks for material problems only: "could be better" is not an issue.

## 6c. Measured accuracy (benchmark)

Run on 2026-11-07, rubric 0.1.0, prompts qc1 0.1.0 / qc2 0.2.0, `gemini-3.5-flash-lite`:

| Mode | Cases | Passed | Recall | Precision | Block accuracy | Exact decisions |
|---|---|---|---|---|---|---|
| Deterministic | 21 run (5 need LLM) | 21 | 100% | 100% | 100% | n/a |
| Full (LLM) | 26 | 25 | 100% (29/29) | 96.7% | 100% | 100% |

**Repeatability** (§20.2), 3 runs × 26 cases, same model and prompts:

| Measure | Result |
|---|---|
| Same release decision in every run | **100%** (26/26) |
| Same set of issues in every run | **96.2%** (25/26) |
| Flaky issues | 2, both in F-008, both QC2 extras pre-declared as acceptable |
| Errored runs | 1 of 78 (I-003, transient; did not recur in 3 reruns) |

**Known limitation:** QC2 sometimes reports a clear but *false* statement as
`unclear_explanation` (F-009), although factual accuracy is QC1's job. The
prompt tells it not to; the lite model does not always comply. Impact: one
duplicate medium-severity note for the instructor; the decision is unchanged.

**What these numbers do and do not show.** The checks and the cases were
written by the same author, and the dataset is one topic. 100% recall here
means the engine does what it was designed to do. It is not yet evidence of
reliability on real lessons; that needs cases from instructors (§19.2).

## 7. Timing rule

- A section's `duration_minutes` is authoritative and **includes** the
  activities and questions placed in it. They are not added again.
- Mandatory content = all sections + mandatory videos.
- Optional videos never count toward the 45-minute limit.

## 8. Version integrity

`LessonVersion.content_hash()` is a SHA-256 of the canonical lesson JSON,
excluding the version number. Every audit and release result stores it. If the
lesson's current hash differs from an audit's hash, that audit is `stale`.
Identical content under a new version number gives the same hash, which
exposes no-op revisions.

## 9. Milestone 1 roadmap

| Step | Scope | Status |
|---|---|---|
| 1 | Config, QC vocabulary | done |
| 2 | Data contracts, sample lesson, this document | done |
| 3 | Deterministic checks: duration, structure, citation existence, coverage matrix, answer keys | done |
| 4 | Scoring weights and decision engine (sections 5, 5a) | done |
| 5 | Benchmark dataset with intentionally broken lessons, plus a detection runner (see `evaluation/README.md`) | done |
| 6 | LLM evaluators: claim verification, consistency, gaps, freshness, instructional review (§6b, §6c) | done |
| 7 | Instructor report (`reporting.py`, `scripts/qc_report.py`) and repeatability check | done |
