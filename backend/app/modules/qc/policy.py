"""Default severity and hard-gate status for every issue type.

This table is the code version of docs/qc_specification.md section 6.
Values are starting points, to be calibrated against the benchmark (Step 5).

Hard gates always stop release, whatever the scores say.
"""

from dataclasses import dataclass

from app.modules.qc.enums import IssueType, Severity

T = IssueType
S = Severity


@dataclass(frozen=True)
class IssuePolicy:
    severity: Severity
    hard_gate: bool = False


ISSUE_POLICY: dict[IssueType, IssuePolicy] = {
    # --- QC1 ---
    T.FABRICATED_CITATION: IssuePolicy(S.CRITICAL, hard_gate=True),
    T.CONTRADICTED_CLAIM: IssuePolicy(S.CRITICAL, hard_gate=True),
    T.UNSUPPORTED_CLAIM: IssuePolicy(S.HIGH),
    T.MISLEADING_CITATION: IssuePolicy(S.HIGH),
    T.INTERNAL_CONTRADICTION: IssuePolicy(S.HIGH),
    T.PARTIALLY_SUPPORTED_CLAIM: IssuePolicy(S.MEDIUM),
    T.MISSING_CITATION: IssuePolicy(S.MEDIUM),
    T.UNVERIFIABLE_CLAIM: IssuePolicy(S.MEDIUM),
    T.INACCESSIBLE_SOURCE: IssuePolicy(S.MEDIUM),
    T.LOW_CREDIBILITY_SOURCE: IssuePolicy(S.MEDIUM),
    T.RESEARCH_GAP: IssuePolicy(S.MEDIUM),
    T.OUTDATED_SOURCE: IssuePolicy(S.LOW),
    # --- QC2 ---
    T.DURATION_EXCEEDED: IssuePolicy(S.HIGH, hard_gate=True),
    T.OBJECTIVE_NOT_ASSESSED: IssuePolicy(S.HIGH, hard_gate=True),
    T.INCORRECT_ANSWER_KEY: IssuePolicy(S.HIGH),
    T.OBJECTIVE_NOT_EXPLAINED: IssuePolicy(S.HIGH),
    T.BLOOM_MISMATCH: IssuePolicy(S.HIGH),
    T.MISSING_SECTION: IssuePolicy(S.MEDIUM),
    T.OBJECTIVE_NOT_EXEMPLIFIED: IssuePolicy(S.MEDIUM),
    T.OBJECTIVE_NOT_PRACTICED: IssuePolicy(S.MEDIUM),
    T.DURATION_MISMATCH: IssuePolicy(S.MEDIUM),
    T.POOR_SEQUENCING: IssuePolicy(S.MEDIUM),
    T.UNCLEAR_EXPLANATION: IssuePolicy(S.MEDIUM),
    T.WEAK_ASSESSMENT: IssuePolicy(S.MEDIUM),
    T.WEAK_EXAMPLE: IssuePolicy(S.LOW),
    T.UNCLEAR_ACTIVITY: IssuePolicy(S.LOW),
    T.ACCESSIBILITY_ISSUE: IssuePolicy(S.LOW),
}
