# Demo lessons

Generated on 2026-11-07 with `gemini-3.5-flash-lite`, lesson prompt 0.5.0, QC prompts
qc1 0.1.0 / qc2 0.3.0, rubric 0.1.0. Each folder is the app's export of one lesson.

| File | What it is |
|---|---|
| `lesson.md` / `lesson.json` | The lesson (readable / structured) |
| `notes.pdf` | The student PDF notes (sections, visuals as tables/steps, test, answer key, references) |
| `summary.png` | The one-page summary image |
| `references.md` | Reference links (websites, books, videos) |
| `qc1_factual_audit.md` | QC Layer 1 report: research and factual accuracy |
| `qc2_instructional_audit.md` | QC Layer 2 report: instructional quality |
| `qc_audits.json` | Both audits and the release decision, machine-readable |
| `research.json` | The research package: sources and the exact evidence passages |
| `v1_*` | (Photosynthesis only) the first version, before the instructor's revision |

## HTTP Requests and Responses (the required sample)

- 7 segments, 45 minutes; 10 visuals; knowledge checks in both core ideas; a "Try it"
  activity; a 10-question test (multiple choice, scenario, order steps, match pairs)
  with hints, misconception-tagged wrong options and review links; review blocks for
  both objectives.
- QC1 100 (7 of 7 claims supported by a specific passage), QC2 100, decision:
  eligible for instructor review.

**Manual fact check.** Every claim was compared with its evidence passage, and every
answer key with the lesson content. All are correct; most claims are near-verbatim from
Wikipedia's *HTTP* and *List of HTTP status codes* articles. One minor note: CL-04 adds
"used to submit data" to the passage's statement that POST is cacheable. The statement
is true, but that part is not in the evidence.

## Photosynthesis (own topic)

- Same structure; QC1 100, QC2 100 for both versions.

**Manual fact check, and what it found.** All claims and answer keys are correct. But
two test questions in **version 1** used the phrase "primary electron donor" for
different things: Q-03 said water (the *ultimate* electron source), and Q-06 said
chlorophyll a (the *primary donor* in the reaction centre). Each is defensible alone;
together they contradict each other and would confuse a learner. **Neither QC layer
flagged it.**

It was fixed with the instructor workflow: Teacher tools, then Improve with AI, with the
instruction "reword Q-03 to ask for the ultimate source of electrons, and Q-06 to ask
which reaction-centre pigment gives up an electron". This produced **version 2**, which
was re-checked automatically (QC1 100, QC2 100). Both versions are kept: compare the
`v1_*` files with the current ones.

This is a real example of why the tool keeps a human in the loop: automated QC catches a
lot, but an instructor's review is the final check.
