"""Turns a layer's issues into rubric subscores."""

from collections.abc import Iterable, Sequence

from app.modules.qc.enums import AuditType, Evaluator
from app.modules.qc.schemas import QCIssue, SubScore
from app.modules.qc.scoring.rubrics import RUBRICS, SEVERITY_PENALTY


def score_rubric(
    audit_type: AuditType, issues: Sequence[QCIssue], evaluators_run: Iterable[Evaluator]
) -> list[SubScore]:
    """One subscore per rubric category.

    - Category not fully evaluated -> score None.
    - Otherwise 100 minus the penalty of each issue in it, never below 0.
    """
    ran = set(evaluators_run)
    subscores = []
    for category in RUBRICS[audit_type]:
        if not category.requires <= ran:
            subscores.append(SubScore(name=category.name, weight=category.weight, score=None))
            continue
        penalty = sum(
            SEVERITY_PENALTY[i.severity] for i in issues if i.issue_type in category.issue_types
        )
        subscores.append(
            SubScore(name=category.name, weight=category.weight, score=max(0, 100 - penalty))
        )
    return subscores
