"""Runs QC end to end: checks -> scored audits -> release decision.

Both layers evaluate the same frozen QCInput and never see each other's
results. Only decide() combines them.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.llm.base import LLMClient, LLMError
from app.modules.qc.enums import AUDIT_OUTCOMES, AuditStatus, AuditType, Evaluator, IssueType
from app.modules.qc.issues import IssueCollector
from app.modules.qc.qc1.llm_review import run_qc1_llm_review
from app.modules.qc.qc1.sources import check_source_credibility
from app.modules.qc.qc2.llm_review import run_qc2_llm_review
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

# Everything run_full_qc() covers: every evaluator the rubrics need.
QC1_FULL = QC1_DETERMINISTIC | {
    Evaluator.CLAIM_VERIFICATION,
    Evaluator.CONSISTENCY_CHECK,
    Evaluator.GAP_DETECTION,
    Evaluator.SOURCE_ASSESSMENT,
}
QC2_FULL = QC2_DETERMINISTIC | {Evaluator.INSTRUCTIONAL_REVIEW}
FULL_EVALUATORS = QC1_FULL | QC2_FULL


@dataclass(frozen=True)
class QCRunResult:
    qc1: AuditReport
    qc2: AuditReport
    # None when an audit could not finish (ERROR): no decision without both audits.
    release: ReleaseResult | None


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
    llm_model: str | None = None,
    prompt_versions: dict[str, str] | None = None,
) -> AuditReport:
    lesson = qc_input.lesson
    evaluators = sorted(set(evaluators))
    subscores = score_rubric(audit_type, issues, evaluators)
    score = weighted_score(subscores)
    return AuditReport(
        audit_id=_audit_id(qc_input, audit_type),
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
        llm_model=llm_model,
        prompt_versions=prompt_versions or {},
    )


def _audit_id(qc_input: QCInput, audit_type: AuditType) -> str:
    lesson = qc_input.lesson
    return f"AUD-{lesson.lesson_id}-V{lesson.version}-{audit_type.value.upper()}"


def error_audit(
    *,
    audit_type: AuditType,
    qc_input: QCInput,
    message: str,
    started_at: datetime,
    completed_at: datetime,
    llm_model: str | None = None,
) -> AuditReport:
    """An audit that could not finish. Says nothing about the lesson; retry it."""
    lesson = qc_input.lesson
    return AuditReport(
        audit_id=_audit_id(qc_input, audit_type),
        audit_type=audit_type,
        lesson_id=lesson.lesson_id,
        version=lesson.version,
        content_hash=lesson.content_hash(),
        rubric_version=RUBRIC_VERSION,
        status=AuditStatus.ERROR,
        error_message=message[:2000],
        started_at=started_at,
        completed_at=completed_at,
        llm_model=llm_model,
    )


def _clock(now: datetime | None) -> Callable[[], datetime]:
    return (lambda: now) if now else (lambda: datetime.now(UTC))


def _run_qc1_full(
    qc_input: QCInput, client: LLMClient, settings: Settings, clock: Callable[[], datetime]
) -> AuditReport:
    started = clock()
    issues = IssueCollector(AuditType.QC1)
    try:
        run_qc1_checks(qc_input, issues)
        check_source_credibility(qc_input.lesson, qc_input.research, issues)
        settled = {
            i.claim_id
            for i in issues.issues
            if i.claim_id
            and i.issue_type in (IssueType.FABRICATED_CITATION, IssueType.UNVERIFIABLE_CLAIM)
        }
        assessments, prompt_version = run_qc1_llm_review(
            qc_input, issues, client, skip_claim_ids=settled, today=started.date()
        )
    except (LLMError, ValidationError) as exc:  # bad model output must never crash QC
        return error_audit(audit_type=AuditType.QC1, qc_input=qc_input, message=str(exc),
                           started_at=started, completed_at=clock(), llm_model=client.model)
    return build_audit(
        audit_type=AuditType.QC1,
        qc_input=qc_input,
        issues=issues.issues,
        evaluators=QC1_FULL,
        min_score=settings.qc1_min_score,
        started_at=started,
        completed_at=clock(),
        claim_assessments=assessments,
        llm_model=client.model,
        prompt_versions={"qc1/llm_review": prompt_version},
    )


def _run_qc2_full(
    qc_input: QCInput, client: LLMClient, settings: Settings, clock: Callable[[], datetime]
) -> AuditReport:
    started = clock()
    issues = IssueCollector(AuditType.QC2)
    try:
        checks = run_qc2_checks(qc_input, max_minutes=settings.max_lesson_minutes, issues=issues)
        prompt_version = run_qc2_llm_review(qc_input, issues, client)
    except (LLMError, ValidationError) as exc:  # bad model output must never crash QC
        return error_audit(audit_type=AuditType.QC2, qc_input=qc_input, message=str(exc),
                           started_at=started, completed_at=clock(), llm_model=client.model)
    return build_audit(
        audit_type=AuditType.QC2,
        qc_input=qc_input,
        issues=issues.issues,
        evaluators=QC2_FULL,
        min_score=settings.qc2_min_score,
        started_at=started,
        completed_at=clock(),
        coverage=checks.coverage,
        llm_model=client.model,
        prompt_versions={"qc2/llm_review": prompt_version},
    )


def run_full_qc(
    qc_input: QCInput,
    client: LLMClient,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
    progress=None,
) -> QCRunResult:
    """Deterministic checks + LLM evaluators for both layers, then decide.

    The two layers run independently on the same frozen input. If either
    cannot finish (LLM down, invalid output), its audit is ERROR and there is
    no release decision until it is rerun.
    """
    settings = settings or get_settings()
    clock = _clock(now)
    qc1 = _run_qc1_full(qc_input, client, settings, clock)
    if progress:
        progress("qc2", qc1)
    qc2 = _run_qc2_full(qc_input, client, settings, clock)
    ready = qc1.status in AUDIT_OUTCOMES and qc2.status in AUDIT_OUTCOMES
    release = decide(qc1, qc2, qc_input.lesson, now=clock()) if ready else None
    return QCRunResult(qc1=qc1, qc2=qc2, release=release)


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
