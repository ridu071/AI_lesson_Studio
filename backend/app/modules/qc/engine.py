"""Runs QC end to end: checks -> scored audits -> release decision.

Both layers evaluate the same frozen QCInput and never see each other's
results. Only decide() combines them.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.config import Settings, get_settings
from app.modules.qc.enums import AuditType, Evaluator
from app.modules.qc.qc1.deterministic import EVALUATORS as QC1_DETERMINISTIC
from app.modules.qc.qc1.deterministic import run_qc1_checks
from app.modules.qc.qc2.deterministic import EVALUATORS as QC2_DETERMINISTIC
from app.modules.qc.qc2.deterministic import run_qc2_checks
from app.modules.qc.schemas import (
    AuditReport,
    ClaimAssessment,
    ObjectiveCoverage,
    QCInput,
    QCIssue,
    ReleaseResult,
    weighted_score,
)
from app.modules.qc.scoring.rubrics import RUBRIC_VERSION
from app.modules.qc.scoring.scorer import score_rubric
from app.modules.qc.validation.decision import audit_outcome, decide


# Everything run_deterministic_qc() covers.
DETERMINISTIC_EVALUATORS = QC1_DETERMINISTIC | QC2_DETERMINISTIC


@dataclass(frozen=True)
class QCRunResult:
    qc1: AuditReport
    qc2: AuditReport
    release: ReleaseResult


def build_audit(
    *,
    audit_type: AuditType,
    qc_input: QCInput,
    issues: Sequence[QCIssue],
    evaluators: Iterable[Evaluator],
    min_score: float,
    started_at: datetime,
    completed_at: datetime,
    coverage: Sequence[ObjectiveCoverage] = (),
    claim_assessments: Sequence[ClaimAssessment] = (),
) -> AuditReport:
    lesson = qc_input.lesson
    evaluators = sorted(set(evaluators))
    subscores = score_rubric(audit_type, issues, evaluators)
    score = weighted_score(subscores)
    return AuditReport(
        audit_id=f"AUD-{lesson.lesson_id}-V{lesson.version}-{audit_type.value.upper()}",
        audit_type=audit_type,
        lesson_id=lesson.lesson_id,
        version=lesson.version,
        content_hash=lesson.content_hash(),
        rubric_version=RUBRIC_VERSION,
        status=audit_outcome(issues, subscores, score, min_score),
        score=score,
        subscores=subscores,
        evaluators=evaluators,
        issues=list(issues),
        claim_assessments=list(claim_assessments),
        coverage=list(coverage),
        started_at=started_at,
        completed_at=completed_at,
    )


def run_deterministic_qc(
    qc_input: QCInput, *, settings: Settings | None = None, now: datetime | None = None
) -> QCRunResult:
    """Run every check that needs no LLM, score both layers and decide.

    Until the LLM evaluators exist (Step 6), most rubric categories are not
    evaluated, so the best possible outcome is MANUAL_REVIEW, never ELIGIBLE.
    """
    settings = settings or get_settings()
    now = now or datetime.now(UTC)

    qc1_checks = run_qc1_checks(qc_input)
    qc2_checks = run_qc2_checks(qc_input, max_minutes=settings.max_lesson_minutes)

    qc1 = build_audit(
        audit_type=AuditType.QC1,
        qc_input=qc_input,
        issues=qc1_checks.issues,
        evaluators=qc1_checks.evaluators,
        min_score=settings.qc1_min_score,
        started_at=now,
        completed_at=now,
    )
    qc2 = build_audit(
        audit_type=AuditType.QC2,
        qc_input=qc_input,
        issues=qc2_checks.issues,
        evaluators=qc2_checks.evaluators,
        min_score=settings.qc2_min_score,
        started_at=now,
        completed_at=now,
        coverage=qc2_checks.coverage,
    )
    return QCRunResult(qc1=qc1, qc2=qc2, release=decide(qc1, qc2, qc_input.lesson, now=now))
