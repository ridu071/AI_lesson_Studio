import pytest

from app.modules.qc.enums import AuditType, IssueType, Severity
from app.modules.qc.issues import IssueCollector
from app.modules.qc.policy import ISSUE_POLICY


def test_every_issue_type_has_a_policy():
    assert set(ISSUE_POLICY) == set(IssueType)


def test_hard_gates_match_the_spec():
    hard_gates = {t for t, p in ISSUE_POLICY.items() if p.hard_gate}
    assert hard_gates == {
        IssueType.FABRICATED_CITATION,
        IssueType.CONTRADICTED_CLAIM,
        IssueType.DURATION_EXCEEDED,
        IssueType.OBJECTIVE_NOT_ASSESSED,
    }


def test_collector_numbers_issues_and_applies_policy():
    issues = IssueCollector(AuditType.QC1)
    issues.add(IssueType.MISSING_CITATION, "Claim CL-001 cites no source.")
    issues.add(IssueType.FABRICATED_CITATION, "Claim CL-002 cites SRC-999.")
    first, second = issues.issues
    assert (first.issue_id, second.issue_id) == ("QC1-001", "QC1-002")
    assert first.severity is Severity.MEDIUM and not first.hard_gate
    assert second.severity is Severity.CRITICAL and second.hard_gate


def test_collector_allows_escalation():
    issues = IssueCollector(AuditType.QC1)
    issue = issues.add(IssueType.MISSING_CITATION, "Key claim has no source.", severity=Severity.HIGH)
    assert issue.severity is Severity.HIGH


def test_collector_refuses_to_weaken_policy():
    issues = IssueCollector(AuditType.QC1)
    with pytest.raises(ValueError, match="below its policy severity"):
        issues.add(IssueType.FABRICATED_CITATION, "Downplayed citation.", severity=Severity.LOW)


def test_collector_refuses_issue_from_other_layer():
    issues = IssueCollector(AuditType.QC1)
    with pytest.raises(ValueError, match="belongs to qc2"):
        issues.add(IssueType.DURATION_EXCEEDED, "QC1 must not judge timing.")


def test_spec_document_matches_policy_table():
    # docs/qc_specification.md section 6 must say exactly what policy.py does.
    import re
    from pathlib import Path

    spec = Path(__file__).resolve().parents[3] / "docs" / "qc_specification.md"
    text = spec.read_text(encoding="utf-8")
    catalogue = text[text.index("## 6. Issue catalogue") : text.index("## 6a.")]
    rows = re.findall(r"^\| `(\w+)`[^|]*\| (\w+) \| (yes)? *\|", catalogue, flags=re.MULTILINE)

    documented = {IssueType(name): (Severity(sev), bool(gate)) for name, sev, gate in rows}
    in_code = {t: (p.severity, p.hard_gate) for t, p in ISSUE_POLICY.items()}
    assert documented == in_code
