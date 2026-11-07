import pytest

from app.modules.qc.enums import ISSUE_TYPE_OWNER, AuditType, Evaluator, IssueType, Severity
from app.modules.qc.issues import IssueCollector
from app.modules.qc.scoring.rubrics import RUBRICS
from app.modules.qc.scoring.scorer import score_rubric

ALL_EVALUATORS = set(Evaluator)


@pytest.mark.parametrize("audit_type", list(AuditType))
def test_rubric_weights_sum_to_one(audit_type):
    assert sum(c.weight for c in RUBRICS[audit_type]) == pytest.approx(1.0)


@pytest.mark.parametrize("audit_type", list(AuditType))
def test_every_issue_type_of_a_layer_is_scored_exactly_once(audit_type):
    owned = {t for t, owner in ISSUE_TYPE_OWNER.items() if owner is audit_type}
    scored = [t for c in RUBRICS[audit_type] for t in c.issue_types]
    assert sorted(scored) == sorted(owned)  # no type missing, none counted twice


def test_workflow_weights():
    qc1 = {c.name: c.weight for c in RUBRICS[AuditType.QC1]}
    assert qc1 == {
        "claim_evidence_support": 0.30,
        "source_credibility": 0.20,
        "citation_integrity": 0.15,
        "cross_source_consistency": 0.15,
        "factual_correctness": 0.15,
        "research_coverage": 0.05,
    }
    assert {c.name: c.weight for c in RUBRICS[AuditType.QC2]}["objective_alignment"] == 0.25


def test_nothing_ran_means_nothing_is_evaluated():
    subscores = score_rubric(AuditType.QC1, [], [])
    assert all(not s.evaluated for s in subscores)


def test_no_issues_with_every_evaluator_scores_100():
    for audit_type in AuditType:
        assert all(s.score == 100 for s in score_rubric(audit_type, [], ALL_EVALUATORS))


def test_deterministic_qc2_only_evaluates_time_feasibility():
    from app.modules.qc.qc2.deterministic import EVALUATORS

    evaluated = [s.name for s in score_rubric(AuditType.QC2, [], EVALUATORS) if s.evaluated]
    assert evaluated == ["time_feasibility"]


def test_issue_penalties_and_floor_at_zero():
    issues = IssueCollector(AuditType.QC2)
    issues.add(IssueType.DURATION_MISMATCH, "Stated 45 but sections add to 50.")  # medium -10
    scores = {s.name: s.score for s in score_rubric(AuditType.QC2, issues.issues, ALL_EVALUATORS)}
    assert scores["time_feasibility"] == 90
    assert scores["clarity"] == 100  # issues only affect their own category

    for _ in range(4):
        issues.add(IssueType.DURATION_EXCEEDED, "Mandatory content is 70 minutes.")  # high -25
    scores = {s.name: s.score for s in score_rubric(AuditType.QC2, issues.issues, ALL_EVALUATORS)}
    assert scores["time_feasibility"] == 0


def test_escalated_severity_costs_more():
    issues = IssueCollector(AuditType.QC2)
    issues.add(IssueType.DURATION_MISMATCH, "Stated time is wrong.", severity=Severity.HIGH)
    scores = {s.name: s.score for s in score_rubric(AuditType.QC2, issues.issues, ALL_EVALUATORS)}
    assert scores["time_feasibility"] == 75


def test_spec_document_rubric_weights_match_code():
    import re
    from pathlib import Path

    spec = Path(__file__).resolve().parents[3] / "docs" / "qc_specification.md"
    text = spec.read_text(encoding="utf-8")
    section = text[text.index("## 5a. Scoring") : text.index("## 6. Issue catalogue")]
    documented = {name: float(w) for name, w in re.findall(r"\| (\w+) \| (0\.\d+) \|", section)}
    in_code = {c.name: c.weight for rubric in RUBRICS.values() for c in rubric}
    assert documented == in_code
