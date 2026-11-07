from datetime import UTC, datetime

from app.llm.base import LLMUnavailableError
from app.modules.qc.engine import FULL_EVALUATORS, run_full_qc
from app.modules.qc.enums import AuditStatus, ClaimVerdict, IssueType, ReleaseDecision, Severity
from tests.fakes import FakeLLM, clean_qc1
from tests.helpers import build_qc_input

NOW = datetime(2026, 11, 7, tzinfo=UTC)
T = IssueType


def run(lesson, research, llm):
    return run_full_qc(build_qc_input(lesson, research), llm, now=NOW)


def qc1_with(claim_id, relations, **extra):
    """A clean QC1 answer, except for one claim."""
    def answer(request):
        out = clean_qc1(request)
        for c in out["claims"]:
            if c["claim_id"] == claim_id:
                c["relations"] = relations
        return out | extra
    return answer


def rel(passage_id, relation):
    return {"passage_id": passage_id, "relation": relation, "reason": "Because the passage says so."}


# --- the full run ---


def test_clean_lesson_with_clean_reviews_is_eligible(lesson_data, research_data):
    llm = FakeLLM()
    result = run(lesson_data, research_data, llm)
    assert result.release.decision is ReleaseDecision.ELIGIBLE
    assert result.qc1.score == 100 and result.qc2.score == 100
    assert set(result.qc1.evaluators) | set(result.qc2.evaluators) == FULL_EVALUATORS
    assert result.qc1.llm_model == "fake-model"
    assert result.qc1.prompt_versions == {"qc1/llm_review": "0.1.0"}
    assert {c.verdict for c in result.qc1.claim_assessments} == {ClaimVerdict.SUPPORTED}


def test_layers_are_independent_calls(lesson_data, research_data):
    llm = FakeLLM()
    run(lesson_data, research_data, llm)
    qc1_call, qc2_call = llm.calls
    assert "QC Layer 1" in qc1_call["system"] and "QC Layer 2" in qc2_call["system"]
    assert "claims_to_verify" not in qc2_call["request"]  # QC2 is not shown QC1's work


def test_model_is_not_told_which_sources_a_claim_cites(lesson_data, research_data):
    # Otherwise it could rubber-stamp the citation it is supposed to check.
    llm = FakeLLM()
    run(lesson_data, research_data, llm)
    for claim in llm.calls[0]["request"]["claims_to_verify"]:
        assert set(claim) == {"claim_id", "text", "claim_type"}


def test_llm_failure_gives_error_audit_and_no_decision(lesson_data, research_data):
    llm = FakeLLM(qc1=LLMUnavailableError("model timed out"))
    result = run(lesson_data, research_data, llm)
    assert result.qc1.status is AuditStatus.ERROR
    assert "timed out" in result.qc1.error_message
    assert result.qc2.status is AuditStatus.PASSED  # the other layer is unaffected
    assert result.release is None


def test_invented_passage_id_is_rejected_then_errors(lesson_data, research_data):
    bad = qc1_with("CL-001", [rel("EV-999", "supports")])
    result = run(lesson_data, research_data, FakeLLM(qc1=[bad, bad]))
    assert result.qc1.status is AuditStatus.ERROR
    assert "unknown passage EV-999" in result.qc1.error_message


def test_skipped_claim_is_rejected(lesson_data, research_data):
    def drops_a_claim(request):
        out = clean_qc1(request)
        out["claims"] = out["claims"][1:]
        return out
    result = run(lesson_data, research_data, FakeLLM(qc1=[drops_a_claim, drops_a_claim]))
    assert result.qc1.status is AuditStatus.ERROR


def test_one_bad_answer_is_corrected_on_retry(lesson_data, research_data):
    bad = qc1_with("CL-001", [rel("EV-999", "supports")])
    result = run(lesson_data, research_data, FakeLLM(qc1=[bad, clean_qc1]))
    assert result.qc1.status is AuditStatus.PASSED


# --- QC1: code turns passage relations into verdicts ---


def test_contradiction_blocks(lesson_data, research_data):
    result = run(lesson_data, research_data, FakeLLM(qc1=qc1_with("CL-002", [rel("EV-002", "contradicts")])))
    [issue] = result.qc1.issues
    assert issue.issue_type is T.CONTRADICTED_CLAIM and issue.claim_id == "CL-002"
    assert issue.severity is Severity.CRITICAL and issue.evidence[0].passage_id == "EV-002"
    assert result.release.decision is ReleaseDecision.BLOCKED


def test_contradiction_wins_even_if_another_passage_supports(lesson_data, research_data):
    llm = FakeLLM(qc1=qc1_with("CL-002", [rel("EV-002", "supports"), rel("EV-003", "contradicts")]))
    assert run(lesson_data, research_data, llm).qc1.issues[0].issue_type is T.CONTRADICTED_CLAIM


def test_support_only_from_an_uncited_source_is_a_misleading_citation(lesson_data, research_data):
    # CL-004 cites SRC-002; pretend only EV-001 (SRC-001) supports it.
    result = run(lesson_data, research_data, FakeLLM(qc1=qc1_with("CL-004", [rel("EV-001", "supports")])))
    [issue] = result.qc1.issues
    assert issue.issue_type is T.MISLEADING_CITATION
    assert "SRC-001" in issue.explanation
    assert result.release.decision is ReleaseDecision.REVISION_REQUIRED


def test_no_support_at_all_is_unsupported(lesson_data, research_data):
    result = run(lesson_data, research_data, FakeLLM(qc1=qc1_with("CL-004", [])))
    [issue] = result.qc1.issues
    assert issue.issue_type is T.UNSUPPORTED_CLAIM
    assert issue.claim_verdict is ClaimVerdict.UNSUPPORTED


def test_partial_support_is_medium(lesson_data, research_data):
    result = run(lesson_data, research_data, FakeLLM(qc1=qc1_with("CL-004", [rel("EV-004", "partially_supports")])))
    [issue] = result.qc1.issues
    assert issue.issue_type is T.PARTIALLY_SUPPORTED_CLAIM and issue.severity is Severity.MEDIUM


def test_uncited_claim_supported_elsewhere_is_only_missing_citation(lesson_data, research_data):
    lesson_data["claims"][3]["source_ids"] = []
    result = run(lesson_data, research_data, FakeLLM())
    assert [i.issue_type for i in result.qc1.issues] == [T.MISSING_CITATION]


def test_claims_settled_by_citation_check_are_not_sent_to_the_model(lesson_data, research_data):
    lesson_data["claims"][3]["source_ids"] = ["SRC-999"]  # fabricated
    llm = FakeLLM()
    result = run(lesson_data, research_data, llm)
    sent = {c["claim_id"] for c in llm.calls[0]["request"]["claims_to_verify"]}
    assert "CL-004" not in sent
    assert [i.issue_type for i in result.qc1.issues] == [T.FABRICATED_CITATION]


def test_contradictions_gaps_and_outdated_sources_become_issues(lesson_data, research_data):
    extra = {
        "internal_contradictions": [{"claim_ids": ["CL-002", "CL-003"], "explanation": "They conflict."}],
        "research_gaps": [{"objective_id": "LO-02", "explanation": "No passage covers it."}],
        "outdated_sources": [{"source_id": "SRC-002", "explanation": "Too old for this topic."}],
    }
    result = run(lesson_data, research_data, FakeLLM(qc1=qc1_with("CL-001", [rel("EV-001", "supports")], **extra)))
    assert [i.issue_type for i in result.qc1.issues] == [
        T.INTERNAL_CONTRADICTION, T.RESEARCH_GAP, T.OUTDATED_SOURCE,
    ]


def test_low_authority_source_is_flagged(lesson_data, research_data):
    research_data["sources"][1]["authority_category"] = "community"
    result = run(lesson_data, research_data, FakeLLM())
    assert [i.issue_type for i in result.qc1.issues] == [T.LOW_CREDIBILITY_SOURCE]


# --- QC2 ---


def qc2_issue(issue_type, **kw):
    return {"issue_type": issue_type, "section_id": None, "question_id": None, "objective_id": None,
            "explanation": "A clear explanation of the problem.", "suggested_fix": "Fix it."} | kw


def test_qc2_issue_uses_policy_severity_and_question_section(lesson_data, research_data):
    llm = FakeLLM(qc2={"issues": [qc2_issue("incorrect_answer_key", question_id="Q-03")]})
    result = run(lesson_data, research_data, llm)
    [issue] = result.qc2.issues
    assert issue.severity is Severity.HIGH  # from policy.py, not the model
    assert issue.section_id == "SEC-07"  # the question's own section
    assert issue.explanation.startswith("Q-03: ")
    assert result.release.decision is ReleaseDecision.REVISION_REQUIRED


def test_qc2_does_not_repeat_a_deterministic_finding(lesson_data, research_data):
    lesson_data["assessments"][0]["answer_key"] = "Labelled and unlabelled data"  # found by code
    llm = FakeLLM(qc2={"issues": [qc2_issue("incorrect_answer_key", question_id="Q-01")]})
    result = run(lesson_data, research_data, llm)
    assert [i.issue_type for i in result.qc2.issues] == [T.INCORRECT_ANSWER_KEY]


def test_qc2_unknown_location_is_rejected(lesson_data, research_data):
    bad = {"issues": [qc2_issue("weak_example", section_id="SEC-99")]}
    result = run(lesson_data, research_data, FakeLLM(qc2=[bad, bad]))
    assert result.qc2.status is AuditStatus.ERROR


def test_qc2_cannot_report_issue_types_reserved_for_code(lesson_data, research_data):
    bad = {"issues": [qc2_issue("duration_exceeded")]}
    result = run(lesson_data, research_data, FakeLLM(qc2=[bad, bad]))
    assert result.qc2.status is AuditStatus.ERROR


def test_terse_model_reasons_do_not_crash_qc(lesson_data, research_data):
    def terse(request):
        out = clean_qc1(request)
        for c in out["claims"]:
            for r in c["relations"]:
                r["reason"] = "Yes."
        return out
    result = run(lesson_data, research_data, FakeLLM(qc1=terse))
    assert result.qc1.status is AuditStatus.PASSED
    assert result.qc1.claim_assessments[0].explanation.startswith("Claim CL-001 is supported")
