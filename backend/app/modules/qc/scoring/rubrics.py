"""QC1 and QC2 rubrics (workflow sections 7.2 and 7.3).

Each category has:
- a weight (starting values from the workflow, to be calibrated in Step 5);
- the issue types that lower its score;
- the evaluators that must ALL have run before the category counts as
  evaluated. A category is evaluated only when every check that could find
  its issues has run. Otherwise "no issues found" would just mean "not checked".

Change RUBRIC_VERSION whenever weights, categories, requirements or penalties
change, so stored audits stay explainable.
"""

from dataclasses import dataclass

from app.modules.qc.enums import AuditType, Evaluator, IssueType, Severity

RUBRIC_VERSION = "0.1.0"

T = IssueType
E = Evaluator

# Points removed from a category's 100 for each issue in it.
SEVERITY_PENALTY: dict[Severity, int] = {
    Severity.CRITICAL: 50,
    Severity.HIGH: 25,
    Severity.MEDIUM: 10,
    Severity.LOW: 3,
}


@dataclass(frozen=True)
class RubricCategory:
    name: str
    weight: float
    issue_types: frozenset[IssueType]
    requires: frozenset[Evaluator]


def _category(name: str, weight: float, issues: set, requires: set) -> RubricCategory:
    return RubricCategory(name, weight, frozenset(issues), frozenset(requires))


QC1_RUBRIC: tuple[RubricCategory, ...] = (
    _category(
        "claim_evidence_support", 0.30,
        {T.UNSUPPORTED_CLAIM, T.PARTIALLY_SUPPORTED_CLAIM, T.UNVERIFIABLE_CLAIM},
        {E.CITATION_CHECK, E.CLAIM_VERIFICATION},
    ),
    _category(
        "source_credibility", 0.20,
        {T.LOW_CREDIBILITY_SOURCE, T.OUTDATED_SOURCE},
        {E.SOURCE_ASSESSMENT},
    ),
    _category(
        "citation_integrity", 0.15,
        {T.FABRICATED_CITATION, T.MISSING_CITATION, T.INACCESSIBLE_SOURCE, T.MISLEADING_CITATION},
        {E.CITATION_CHECK, E.CLAIM_VERIFICATION},  # misleading citations need the LLM
    ),
    _category(
        "cross_source_consistency", 0.15,
        {T.INTERNAL_CONTRADICTION},
        {E.CONSISTENCY_CHECK},
    ),
    _category(
        "factual_correctness", 0.15,
        {T.CONTRADICTED_CLAIM},
        {E.CLAIM_VERIFICATION},
    ),
    _category(
        "research_coverage", 0.05,
        {T.RESEARCH_GAP},
        {E.GAP_DETECTION},
    ),
)

QC2_RUBRIC: tuple[RubricCategory, ...] = (
    _category(
        "objective_alignment", 0.25,
        {T.OBJECTIVE_NOT_EXPLAINED, T.OBJECTIVE_NOT_ASSESSED, T.BLOOM_MISMATCH},
        {E.COVERAGE_CHECK, E.ASSESSMENT_CHECK, E.INSTRUCTIONAL_REVIEW},
    ),
    _category(
        "clarity", 0.15,
        {T.UNCLEAR_EXPLANATION},
        {E.INSTRUCTIONAL_REVIEW},
    ),
    _category(
        "learning_progression", 0.15,
        {T.MISSING_SECTION, T.POOR_SEQUENCING},
        {E.STRUCTURE_CHECK, E.INSTRUCTIONAL_REVIEW},
    ),
    _category(
        "examples", 0.10,
        {T.OBJECTIVE_NOT_EXEMPLIFIED, T.WEAK_EXAMPLE},
        {E.COVERAGE_CHECK, E.INSTRUCTIONAL_REVIEW},
    ),
    _category(
        "activities", 0.10,
        {T.OBJECTIVE_NOT_PRACTICED, T.UNCLEAR_ACTIVITY},
        {E.COVERAGE_CHECK, E.INSTRUCTIONAL_REVIEW},
    ),
    _category(
        "assessment_effectiveness", 0.15,
        {T.INCORRECT_ANSWER_KEY, T.WEAK_ASSESSMENT},
        {E.ASSESSMENT_CHECK, E.INSTRUCTIONAL_REVIEW},
    ),
    _category(
        "engagement_accessibility", 0.05,
        {T.ACCESSIBILITY_ISSUE},
        {E.INSTRUCTIONAL_REVIEW},
    ),
    _category(
        "time_feasibility", 0.05,
        {T.DURATION_EXCEEDED, T.DURATION_MISMATCH},
        {E.DURATION_CHECK},
    ),
)

RUBRICS: dict[AuditType, tuple[RubricCategory, ...]] = {
    AuditType.QC1: QC1_RUBRIC,
    AuditType.QC2: QC2_RUBRIC,
}
