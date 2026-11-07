"""QC input and output contracts.

Input:  QCInput (the frozen lesson version + its research package).
Output: one AuditReport per layer (QC1, QC2), then one ReleaseResult.

These models also enforce the release rules that must never be broken,
whatever code builds them (see docs/qc_specification.md, section 5):
- A claim cannot be "supported" without citing an evidence passage.
- A PASSED audit cannot contain a blocking or high-severity issue.
- An ELIGIBLE release cannot have blocking issues.
"""

from collections.abc import Sequence
from typing import Annotated

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from app.modules.qc.enums import (
    AUDIT_OUTCOMES,
    ISSUE_TYPE_OWNER,
    AuditStatus,
    AuditType,
    ClaimVerdict,
    Evaluator,
    IssueType,
    ReleaseDecision,
    Severity,
)
from app.schemas.common import (
    ClaimId,
    ContractModel,
    LessonId,
    NonEmptyStr,
    ObjectiveId,
    PassageId,
    SectionId,
    Sha256Hex,
    SourceId,
    find_duplicates,
)
from app.schemas.lesson import LessonVersion
from app.schemas.research import ResearchPackage

IssueId = Annotated[str, StringConstraints(pattern=r"^QC[12]-\d+$")]

WEIGHT_TOLERANCE = 1e-6
SCORE_TOLERANCE = 0.01

# Verdicts that make a statement about the evidence, so they must point to it.
_VERDICTS_NEEDING_EVIDENCE = frozenset(
    {ClaimVerdict.SUPPORTED, ClaimVerdict.PARTIALLY_SUPPORTED, ClaimVerdict.CONTRADICTED}
)


# --------------------------------------------------------------------- input


class QCInput(ContractModel):
    """Everything QC needs. Both layers receive the same frozen snapshot."""

    request_objective: str = Field(min_length=10, max_length=1000)  # the student's original words
    lesson: LessonVersion
    research: ResearchPackage


# ------------------------------------------------------------ building blocks


class EvidenceRef(ContractModel):
    source_id: SourceId
    passage_id: PassageId | None = None
    note: str | None = None


class Recommendation(ContractModel):
    action: NonEmptyStr  # what should change
    suggested_text: str | None = None  # replacement text, if QC can propose one
    auto_applicable: bool = False  # may the revision engine apply it without a human?


class QCIssue(ContractModel):
    issue_id: IssueId  # "QC1-001", "QC2-004", ...
    audit_type: AuditType
    issue_type: IssueType
    severity: Severity
    # Set by the check that raises the issue, for rules that must always stop
    # release (e.g. fabricated citation, lesson over 45 minutes).
    hard_gate: bool = False
    # The engine cannot decide this one (e.g. the only evidence is unreadable).
    # Leads to MANUAL_REVIEW unless something blocks first.
    requires_manual_review: bool = False
    explanation: str = Field(min_length=10)
    section_id: SectionId | None = None
    claim_id: ClaimId | None = None
    objective_id: ObjectiveId | None = None
    claim_verdict: ClaimVerdict | None = None
    evidence: list[EvidenceRef] = []
    recommendation: Recommendation | None = None

    @property
    def blocks_release(self) -> bool:
        return self.hard_gate or self.severity is Severity.CRITICAL

    @model_validator(mode="after")
    def _check_ownership(self) -> "QCIssue":
        owner = ISSUE_TYPE_OWNER[self.issue_type]
        if owner is not self.audit_type:
            raise ValueError(
                f"{self.issue_id}: issue type '{self.issue_type}' belongs to {owner}, "
                f"not {self.audit_type}"
            )
        if not self.issue_id.lower().startswith(self.audit_type.value):
            raise ValueError(f"{self.issue_id}: issue ID prefix must match {self.audit_type}")
        if self.claim_verdict is not None and self.audit_type is not AuditType.QC1:
            raise ValueError(f"{self.issue_id}: only QC1 issues carry a claim verdict")
        return self


class ClaimAssessment(ContractModel):
    """QC1's verdict on one claim."""

    claim_id: ClaimId
    verdict: ClaimVerdict
    evidence: list[EvidenceRef] = []
    explanation: str = Field(min_length=10)

    @model_validator(mode="after")
    def _evidence_before_confidence(self) -> "ClaimAssessment":
        # Design principle 1: a claim cannot be judged against the evidence
        # without pointing to the exact passage that was used.
        if self.verdict in _VERDICTS_NEEDING_EVIDENCE and not any(
            e.passage_id for e in self.evidence
        ):
            raise ValueError(
                f"{self.claim_id}: verdict '{self.verdict}' must cite at least one evidence passage"
            )
        return self


class ObjectiveCoverage(ContractModel):
    """One row of QC2's coverage matrix (workflow section 7.3)."""

    objective_id: ObjectiveId
    explained: bool
    exemplified: bool
    practiced: bool
    assessed: bool

    @property
    def is_complete(self) -> bool:
        return self.explained and self.exemplified and self.practiced and self.assessed


class SubScore(ContractModel):
    name: NonEmptyStr  # rubric category, e.g. "claim_evidence_support"
    weight: float = Field(gt=0, le=1)
    # None = not evaluated yet (the checks this category needs have not run).
    # We never invent a number for something that was not measured.
    score: float | None = Field(default=None, ge=0, le=100)

    @property
    def evaluated(self) -> bool:
        return self.score is not None


def weighted_score(subscores: Sequence[SubScore]) -> float | None:
    """The layer score: sum of weight x subscore, rounded to 2 decimals.

    None if there are no subscores or ANY category is not evaluated: a partial
    score would look like a real one.
    """
    if not subscores or not all(s.evaluated for s in subscores):
        return None
    return round(sum(s.weight * s.score for s in subscores), 2)


# -------------------------------------------------------------------- output


class AuditReport(ContractModel):
    """The complete result of one QC layer for one exact lesson version."""

    audit_id: NonEmptyStr
    audit_type: AuditType
    # Pins the audit to an exact version. If the lesson's hash no longer matches,
    # this audit is STALE.
    lesson_id: LessonId
    version: int = Field(ge=1)
    content_hash: Sha256Hex
    rubric_version: NonEmptyStr
    status: AuditStatus
    score: float | None = Field(default=None, ge=0, le=100)  # must equal weighted_score(subscores)
    subscores: list[SubScore] = []
    # Which checks actually ran. Shows the instructor what was NOT checked.
    evaluators: list[Evaluator] = []
    # Exactly which model and prompt versions produced this audit (workflow
    # table qc_evaluation_runs), so old audits stay explainable.
    llm_model: str | None = None
    prompt_versions: dict[str, str] = {}
    issues: list[QCIssue] = []
    claim_assessments: list[ClaimAssessment] = []  # QC1 only
    coverage: list[ObjectiveCoverage] = []  # QC2 only
    started_at: AwareDatetime | None = None
    completed_at: AwareDatetime | None = None
    error_message: str | None = None

    @model_validator(mode="after")
    def _check_consistency(self) -> "AuditReport":
        problems = (
            self._score_problems()
            + self._issue_problems()
            + self._layer_problems()
            + self._status_problems()
        )
        if problems:
            raise ValueError(f"Audit {self.audit_id} is invalid: " + "; ".join(problems))
        return self

    def _score_problems(self) -> list[str]:
        problems = [
            f"duplicate subscore {d}" for d in find_duplicates(s.name for s in self.subscores)
        ]
        if not self.subscores:
            if self.score is not None:
                problems.append("score given without subscores")
            return problems
        total_weight = sum(s.weight for s in self.subscores)
        if abs(total_weight - 1) > WEIGHT_TOLERANCE:
            problems.append(f"subscore weights must sum to 1, got {total_weight:.4f}")
        expected = weighted_score(self.subscores)
        if expected is None and self.score is not None:
            problems.append("score must be empty while any subscore is not evaluated")
        elif expected is not None and (
            self.score is None or abs(self.score - expected) > SCORE_TOLERANCE
        ):
            problems.append(f"score must equal the weighted subscores ({expected})")
        return problems

    def _issue_problems(self) -> list[str]:
        problems = [
            f"duplicate issue id {d}" for d in find_duplicates(i.issue_id for i in self.issues)
        ]
        problems += [
            f"{i.issue_id} is a {i.audit_type} issue inside a {self.audit_type} audit"
            for i in self.issues
            if i.audit_type is not self.audit_type
        ]
        return problems

    def _layer_problems(self) -> list[str]:
        problems = []
        if self.audit_type is AuditType.QC2 and self.claim_assessments:
            problems.append("claim assessments belong to QC1 only")
        if self.audit_type is AuditType.QC1 and self.coverage:
            problems.append("objective coverage belongs to QC2 only")
        problems += [
            f"claim {d} assessed twice"
            for d in find_duplicates(c.claim_id for c in self.claim_assessments)
        ]
        problems += [
            f"objective {d} appears twice in coverage"
            for d in find_duplicates(c.objective_id for c in self.coverage)
        ]
        return problems

    def _status_problems(self) -> list[str]:
        problems = []
        if self.status in AUDIT_OUTCOMES:
            problems += self._outcome_problems()
        if self.status is AuditStatus.PASSED:
            problems += self._passed_problems()
        if self.status is AuditStatus.ERROR and not self.error_message:
            problems.append("an error audit must explain what went wrong in error_message")
        if self.started_at and self.completed_at and self.completed_at < self.started_at:
            problems.append("completed_at is before started_at")
        return problems

    def _outcome_problems(self) -> list[str]:
        problems = []
        if not self.subscores:
            problems.append(f"a {self.status} audit must include its subscores")
        if self.completed_at is None:
            problems.append(f"a {self.status} audit must have completed_at")
        # BLOCKED if and only if something blocks release.
        has_blocker = any(i.blocks_release for i in self.issues)
        if has_blocker and self.status is not AuditStatus.BLOCKED:
            problems.append(f"an audit with a blocking issue must be blocked, not {self.status}")
        if self.status is AuditStatus.BLOCKED and not has_blocker:
            problems.append("a blocked audit must contain a blocking issue")
        return problems

    def _passed_problems(self) -> list[str]:
        problems = []
        unevaluated = [s.name for s in self.subscores if not s.evaluated]
        if unevaluated:
            problems.append(
                "a passed audit must have every category evaluated; missing: "
                + ", ".join(unevaluated)
            )
        bad = [
            i.issue_id
            for i in self.issues
            if i.blocks_release or i.severity is Severity.HIGH or i.requires_manual_review
        ]
        if bad:
            problems.append(
                "a passed audit cannot contain blocking, high-severity or "
                "manual-review issues: " + ", ".join(bad)
            )
        return problems

    def blocking_issues(self) -> list[QCIssue]:
        return [i for i in self.issues if i.blocks_release]


class ReleaseResult(ContractModel):
    """The combined decision for one lesson version, from both audits.

    ELIGIBLE means "may go to the instructor", never "approved".
    """

    lesson_id: LessonId
    version: int = Field(ge=1)
    content_hash: Sha256Hex
    qc1_audit_id: NonEmptyStr
    qc2_audit_id: NonEmptyStr
    decision: ReleaseDecision
    reasons: list[NonEmptyStr] = Field(min_length=1)  # every decision is explained
    blocking_issue_ids: list[IssueId] = []
    decided_at: AwareDatetime

    @model_validator(mode="after")
    def _check_decision(self) -> "ReleaseResult":
        if self.decision is ReleaseDecision.ELIGIBLE and self.blocking_issue_ids:
            raise ValueError("an eligible lesson cannot have blocking issues")
        if self.decision is ReleaseDecision.BLOCKED and not self.blocking_issue_ids:
            raise ValueError("a blocked lesson must name the issues that block it")
        return self
