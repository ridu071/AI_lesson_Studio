from app.modules.qc.enums import ClaimVerdict, IssueType, Severity
from app.modules.qc.qc1.deterministic import run_qc1_checks
from tests.helpers import build_qc_input


def run(lesson, research):
    return run_qc1_checks(build_qc_input(lesson, research)).issues


def types(issues):
    return [i.issue_type for i in issues]


def test_valid_lesson_has_no_citation_issues(lesson_data, research_data):
    assert run(lesson_data, research_data) == []


# --- fabricated citations (E2E-005) ---


def test_fabricated_citation_in_claim_is_a_critical_hard_gate(lesson_data, research_data):
    lesson_data["claims"][3]["source_ids"] = ["SRC-999"]  # CL-004
    [issue] = run(lesson_data, research_data)
    assert issue.issue_type is IssueType.FABRICATED_CITATION
    assert issue.severity is Severity.CRITICAL
    assert issue.hard_gate and issue.blocks_release
    assert issue.claim_id == "CL-004"
    assert "SRC-999" in issue.explanation


def test_fabricated_citation_in_section_is_detected(lesson_data, research_data):
    lesson_data["sections"][3]["source_ids"] = ["SRC-002", "SRC-404"]
    [issue] = run(lesson_data, research_data)
    assert issue.issue_type is IssueType.FABRICATED_CITATION
    assert issue.section_id == "SEC-04"


def test_fabricated_citation_in_video_is_detected(lesson_data, research_data):
    lesson_data["videos"][0]["source_id"] = "SRC-777"
    assert types(run(lesson_data, research_data)) == [IssueType.FABRICATED_CITATION]


def test_claim_citing_only_fabricated_sources_is_not_double_reported(lesson_data, research_data):
    lesson_data["claims"][0]["source_ids"] = ["SRC-999"]
    # One fabricated_citation, not also an "unverifiable" issue for the same claim.
    assert types(run(lesson_data, research_data)) == [IssueType.FABRICATED_CITATION]


# --- missing citations ---


def test_factual_claim_without_source_is_flagged(lesson_data, research_data):
    lesson_data["claims"][3]["source_ids"] = []
    [issue] = run(lesson_data, research_data)
    assert issue.issue_type is IssueType.MISSING_CITATION
    assert issue.claim_id == "CL-004"
    assert not issue.blocks_release


def test_hypothetical_example_needs_no_source(lesson_data, research_data):
    claim = lesson_data["claims"][5]
    assert claim["claim_type"] == "hypothetical_example" and "source_ids" not in claim
    assert run(lesson_data, research_data) == []


# --- unreadable evidence ---


def test_claim_backed_only_by_metadata_needs_manual_review(lesson_data, research_data):
    # SRC-003 is a video we only know the title of. It cannot prove a claim.
    lesson_data["claims"][3]["source_ids"] = ["SRC-003"]
    [issue] = run(lesson_data, research_data)
    assert issue.issue_type is IssueType.UNVERIFIABLE_CLAIM
    assert issue.requires_manual_review
    assert issue.claim_verdict is ClaimVerdict.UNVERIFIABLE


def test_inaccessible_source_is_reported_and_its_claims_become_unverifiable(
    lesson_data, research_data
):
    research_data["sources"][0]["access_status"] = "inaccessible"  # SRC-001 backs CL-001, CL-002
    issues = run(lesson_data, research_data)
    assert types(issues) == [
        IssueType.INACCESSIBLE_SOURCE,
        IssueType.UNVERIFIABLE_CLAIM,
        IssueType.UNVERIFIABLE_CLAIM,
    ]
    assert [i.claim_id for i in issues[1:]] == ["CL-001", "CL-002"]


def test_inaccessible_source_with_a_readable_alternative_is_not_unverifiable(
    lesson_data, research_data
):
    research_data["sources"][0]["access_status"] = "inaccessible"
    lesson_data["claims"][0]["source_ids"] = ["SRC-001", "SRC-002"]
    lesson_data["claims"][1]["source_ids"] = ["SRC-001", "SRC-002"]
    assert types(run(lesson_data, research_data)) == [IssueType.INACCESSIBLE_SOURCE]
