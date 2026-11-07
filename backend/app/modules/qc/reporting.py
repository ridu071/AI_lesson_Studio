"""Human-readable QC report for the instructor (workflow sections 9.3-9.4).

Built only from the audit JSON plus the QC input, so the report can never
say something the audits do not. Instructor-only: it contains internal QC
detail that must not be shown to anonymous students (workflow section 4.4).
"""

from app.modules.qc.engine import QCRunResult
from app.modules.qc.enums import AuditStatus, ReleaseDecision, severity_rank
from app.modules.qc.schemas import AuditReport, EvidenceRef, QCInput, QCIssue
from app.modules.qc.scoring.rubrics import RUBRICS

DECISION_TEXT = {
    ReleaseDecision.ELIGIBLE: "ELIGIBLE FOR INSTRUCTOR REVIEW - no blocking problems found",
    ReleaseDecision.REVISION_REQUIRED: "REVISION REQUIRED - fixable problems must be corrected first",
    ReleaseDecision.MANUAL_REVIEW: "MANUAL REVIEW - the engine cannot decide; a human must judge",
    ReleaseDecision.BLOCKED: "BLOCKED - a hard rule failed; this version cannot be released",
}
STATUS_TEXT = {
    AuditStatus.PASSED: "passed",
    AuditStatus.NEEDS_REVISION: "needs revision",
    AuditStatus.MANUAL_REVIEW: "needs manual review",
    AuditStatus.BLOCKED: "blocked",
    AuditStatus.ERROR: "could not finish (error)",
}
LAYER_TITLE = {"qc1": "QC1 - Factual accuracy", "qc2": "QC2 - Instructional quality"}
MAX_QUOTE = 300


def _quote(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= MAX_QUOTE else text[: MAX_QUOTE - 3] + "..."


def _location(issue: QCIssue) -> str:
    parts = [p for p in (issue.section_id, issue.claim_id, issue.objective_id) if p]
    return ", ".join(parts) or "whole lesson"


def _evidence_lines(qc_input: QCInput, refs: list[EvidenceRef]) -> list[str]:
    lines = []
    for ref in refs:
        source = qc_input.research.find_source(ref.source_id)
        title = f" ({source.title})" if source else ""
        if ref.passage_id:
            passage = qc_input.research.find_passage(ref.passage_id)
            text = f': "{_quote(passage.text)}"' if passage else ""
            lines.append(f"  - Evidence {ref.passage_id} from {ref.source_id}{title}{text}")
        else:
            lines.append(f"  - Source {ref.source_id}{title}")
    return lines


def _issue_block(qc_input: QCInput, issue: QCIssue) -> list[str]:
    flags = []
    if issue.blocks_release:
        flags.append("BLOCKS RELEASE")
    if issue.requires_manual_review:
        flags.append("NEEDS HUMAN JUDGEMENT")
    flag_text = f" - **{' / '.join(flags)}**" if flags else ""
    lines = [
        f"- **{issue.issue_id} [{issue.severity.upper()}] {issue.issue_type}**{flag_text}",
        f"  - Where: {_location(issue)}",
        f"  - Why: {issue.explanation}",
    ]
    lines += _evidence_lines(qc_input, issue.evidence)
    if issue.recommendation:
        auto = " (can be applied automatically)" if issue.recommendation.auto_applicable else ""
        lines.append(f"  - Suggested fix{auto}: {issue.recommendation.action}")
    return lines


def _scores_table(audit: AuditReport) -> list[str]:
    requires = {c.name: c.requires for c in RUBRICS[audit.audit_type]}
    ran = set(audit.evaluators)
    lines = ["| Category | Weight | Score |", "|---|---|---|"]
    for s in audit.subscores:
        if s.evaluated:
            score = f"{s.score:g}"
        else:
            missing = ", ".join(sorted(requires[s.name] - ran))
            score = f"not evaluated (needs {missing})"
        lines.append(f"| {s.name} | {s.weight:.0%} | {score} |")
    return lines


def _layer_section(qc_input: QCInput, audit: AuditReport) -> list[str]:
    score = "not complete" if audit.score is None else f"{audit.score:g} / 100"
    lines = [
        f"## {LAYER_TITLE[audit.audit_type]}",
        "",
        f"Status: **{STATUS_TEXT.get(audit.status, audit.status)}** - score: **{score}**",
        "",
    ]
    if audit.status is AuditStatus.ERROR:
        return lines + [f"The audit could not finish: {audit.error_message}",
                        "It says nothing about the lesson. Rerun it.", ""]

    lines += _scores_table(audit) + [""]
    issues = sorted(audit.issues, key=lambda i: -severity_rank(i.severity))
    if issues:
        lines += [f"### Issues ({len(issues)})", ""]
        for issue in issues:
            lines += _issue_block(qc_input, issue)
        lines.append("")
    else:
        lines += ["No issues found.", ""]

    if audit.claim_assessments:
        cites = {c.claim_id: set(c.source_ids) for c in qc_input.lesson.claims}
        lines += ["### Claim verification", "", "| Claim | Verdict | Evidence |", "|---|---|---|"]
        for c in audit.claim_assessments:
            evidence = ", ".join(
                f"{e.passage_id} ({e.source_id}"
                + ("" if e.source_id in cites.get(c.claim_id, set()) else ", not cited by the claim")
                + ")"
                for e in c.evidence
                if e.passage_id
            ) or "-"
            lines.append(f"| {c.claim_id} | {c.verdict} | {evidence} |")
        lines.append("")

    if audit.coverage:
        lines += ["### Objective coverage", "",
                  "| Objective | Explained | Example | Activity | Assessed |", "|---|---|---|---|---|"]
        mark = {True: "yes", False: "**NO**"}
        for row in audit.coverage:
            lines.append(f"| {row.objective_id} | {mark[row.explained]} | {mark[row.exemplified]} | "
                         f"{mark[row.practiced]} | {mark[row.assessed]} |")
        lines.append("")
    return lines


def render_markdown(qc_input: QCInput, run: QCRunResult) -> str:
    lesson = qc_input.lesson
    lines = [
        f"# QC report: {lesson.title}",
        "",
        f"Lesson {lesson.lesson_id}, version {lesson.version} - content hash "
        f"`{lesson.content_hash()[:12]}` - learner level: {lesson.learner_level}",
        "",
        "*Instructor only. Contains internal QC detail; never show this to students.*",
        "",
    ]
    if run.release is None:
        lines += ["## Decision: NONE YET", "",
                  "At least one audit could not finish. Rerun QC before deciding.", ""]
    else:
        lines += [f"## Decision: {DECISION_TEXT[run.release.decision]}", ""]
        lines += [f"- {reason}" for reason in run.release.reasons]
        lines += ["", "Eligible is not approved: only the instructor approves and publishes.", ""]

    for audit in (run.qc1, run.qc2):
        lines += _layer_section(qc_input, audit)

    lines += ["---", "", "**How this report was produced**", ""]
    for audit in (run.qc1, run.qc2):
        prompts = ", ".join(f"{k} {v}" for k, v in audit.prompt_versions.items()) or "none"
        lines.append(
            f"- {audit.audit_type.upper()}: rubric {audit.rubric_version}, "
            f"model {audit.llm_model or 'none (deterministic checks only)'}, prompts: {prompts}; "
            f"checks run: {', '.join(audit.evaluators) or 'none'}"
        )
    return "\n".join(lines) + "\n"
