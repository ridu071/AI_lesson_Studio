# QC benchmark

Measures whether QC finds real problems, explains them, and avoids blocking
good lessons (workflow §20.2, §25).

```
cd backend
python scripts/run_benchmark.py          # deterministic, free, instant
python scripts/run_benchmark.py --llm    # full QC with the configured LLM
```

## Layout

| Folder | Contents |
|---|---|
| `benchmark_lessons/<name>/` | A base lesson: `lesson.json`, `research.json`, `request.json` |
| `control_cases/` | `C-*`: clean lessons and multi-problem cases |
| `factual_test_cases/` | `F-*`: QC1 problems (citations, evidence, claims) |
| `instructional_test_cases/` | `I-*`: QC2 problems (time, coverage, assessments, structure) |
| `evaluation_results/` | Runner output (`latest.json`, not committed) |
| `expected_audits/` | Reserved for full expected-audit snapshots (not used yet) |

## A case file

```json
{
  "case_id": "F-001",
  "title": "Fabricated citation on a factual claim",
  "rationale": "Why this is (or is not) a problem.",
  "base": "ml_intro",
  "requires_evaluators": [],
  "mutations": [
    {"op": "replace", "path": "/lesson/claims/3/source_ids", "value": ["SRC-999"]}
  ],
  "expected": {
    "decision": "blocked",
    "issues": [{"issue_type": "fabricated_citation", "claim_id": "CL-004"}]
  }
}
```

- `mutations` are JSON Patch operations (`add`, `replace`, `remove`) applied
  to `{request_objective, lesson, research}`. A path that does not exist is an error.
- `expected.issues` lists **exactly** the issues QC should report. Extra issues
  count as false alarms. Location fields that are given (`claim_id`,
  `section_id`, `objective_id`) must match.
- `expected.decision` is what a human reviewer would decide with **all** checks
  available.
- `requires_evaluators`: the case is skipped until those evaluators exist
  (e.g. `claim_verification` arrives with the LLM in Step 6).
- An expected issue can say `"needs": "gap_detection"` (or another evaluator):
  it is required only when that evaluator runs, and ignored otherwise.
- `expected.acceptable` lists defensible extra findings that are neither
  required nor counted as false alarms. Declare them when writing the case.

## Changing an expectation after a run

Allowed only when the evidence shows the expectation was wrong (adjudication),
never to make a run pass. Record why in the case's `rationale`. Example: F-006
originally claimed SRC-002 backed CL-001/CL-002. It does not, and the LLM
correctly reported them unsupported, so the case was fixed.

## How results are judged

- A case passes when every expected issue is found, nothing else is reported,
  and the decision is right.
- While some rubric categories cannot be evaluated (no LLM yet), only
  "blocked vs not blocked" is compared. Exact decisions are compared once
  every evaluator runs.
- Controls (cases expecting no issues) measure false alarms, which matter as
  much as misses: a QC that blocks good lessons is not usable.

## Adding cases

Most valuable are cases written by **someone other than the QC author**,
especially from real instructor corrections (workflow §19.2). Cases written
by the person who wrote the checks mostly confirm the checks do what was
intended.

The sources in `ml_intro` are synthetic (`example.org`) and must never be
shown to students.
