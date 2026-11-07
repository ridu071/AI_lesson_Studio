# Test fixtures

`valid_lesson.json` and `valid_research.json` are a **known-good** lesson and its
research package. Tests load them, change one thing, and check the result.

The lesson content is accurate, but the **sources are synthetic test data**:
`example.org` URLs and invented publishers ("Example University"). They are not
real citations and must never be shown to students as references.

The lesson is designed to pass every check:

- Section durations add up to 45 minutes and match `stated_duration_minutes`.
- Every objective is explained, has an example, an activity and an assessment.
- Every factual or definition claim cites a source with a supporting passage.
- The supplementary video (SRC-003) is `metadata_only`: it is optional and is
  not used as evidence.
