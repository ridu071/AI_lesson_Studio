# QC Engine Specification

Status: **Milestone 1, Step 3: deterministic checks.** Rubric version `0.1.0`.

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
  its subscores, issues, QC1 claim verdicts and the QC2 objective coverage matrix.
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

Applied in this order. The first rule that matches wins.

| # | Condition | Decision |
|---|---|---|
| 1 | Any issue is `critical` or a hard gate | **blocked** |
| 2 | Any issue has `requires_manual_review`, or either audit is `manual_review` | **manual_review** |
| 3 | Any `high` issue, or QC1 or QC2 score below its threshold (80) | **revision_required** |
| 4 | Otherwise | **eligible_for_instructor_review** |

- `medium` and `low` issues never block. They appear as recommendations.
- An `error` or `stale` audit produces **no decision**: rerun it first.
- "Eligible" is not "approved". Only the instructor approves (workflow §9.6).

These rules are also enforced by the contracts themselves:

- A `passed` audit cannot contain a high, critical, hard-gate or manual-review issue.
- An `eligible` release cannot list blocking issues.
- A `blocked` release must list them.
- A claim verdict of `supported`, `partially_supported` or `contradicted` must
  cite an evidence passage ("evidence before confidence").
- The score must equal the weighted subscores, and the weights must sum to 1.

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
| `low_credibility_source` | medium | | later |
| `research_gap` | medium | | LLM |
| `outdated_source` | low | | later |

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
| 4 | Scoring weights and decision engine (section 5) | next |
| 5 | Benchmark dataset with intentionally broken lessons, plus a detection runner | |
| 6 | LLM modules: claim extraction and verification, clarity, Bloom alignment | |
| 7 | Human-readable reports and a repeatability check | |
