"""QC1 LLM review: claim verification, consistency, research gaps, freshness.

The model only judges how each evidence passage relates to each claim
(supports / partially supports / contradicts). The VERDICT is then decided
by code from those relations, so the rules are fixed and testable:

  any passage contradicts the claim                  -> contradicted_claim (critical)
  a passage from a CITED source supports it          -> supported, no issue
  a cited passage only partially supports it         -> partially_supported_claim
  only passages from UNCITED sources support it      -> misleading_citation
      (if the claim cites nothing, missing_citation was already reported)
  nothing supports it                                -> unsupported_claim

The model never sees which sources each claim cites, so its relation
judgements cannot be biased by the citations it is meant to check.
"""

from datetime import date
from typing import Literal

from pydantic import Field

from app.llm.base import LLMClient, LLMInvalidOutputError, call_structured, to_prompt_json
from app.llm.prompts import load_prompt
from app.modules.qc.enums import ClaimVerdict, IssueType
from app.modules.qc.issues import IssueCollector
from app.modules.qc.qc1.citations import EVIDENCE_REQUIRED, has_usable_evidence
from app.modules.qc.schemas import ClaimAssessment, EvidenceRef, QCInput
from app.schemas.common import ContractModel, NonEmptyStr
from app.schemas.enums import ClaimType
from app.schemas.lesson import Claim

PROMPT_PATH = "qc1/llm_review.md"

Relation = Literal["supports", "partially_supports", "contradicts"]


# ------------------------------------------------------------ model output


class PassageRelation(ContractModel):
    passage_id: str
    relation: Relation
    reason: NonEmptyStr


class ClaimRelations(ContractModel):
    claim_id: str
    relations: list[PassageRelation]


class Contradiction(ContractModel):
    claim_ids: list[str] = Field(min_length=2)
    explanation: NonEmptyStr


class ResearchGap(ContractModel):
    objective_id: str
    explanation: NonEmptyStr


class OutdatedSource(ContractModel):
    source_id: str
    explanation: NonEmptyStr


class QC1Review(ContractModel):
    claims: list[ClaimRelations]
    internal_contradictions: list[Contradiction]
    research_gaps: list[ResearchGap]
    outdated_sources: list[OutdatedSource]


def _array(item_properties: dict, required: list[str]) -> dict:
    return {
        "type": "array",
        "items": {"type": "object", "properties": item_properties, "required": required},
    }


_TEXT = {"type": "string"}
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": _array(
            {
                "claim_id": _TEXT,
                "relations": _array(
                    {
                        "passage_id": _TEXT,
                        "relation": {
                            "type": "string",
                            "enum": ["supports", "partially_supports", "contradicts"],
                        },
                        "reason": _TEXT,
                    },
                    ["passage_id", "relation", "reason"],
                ),
            },
            ["claim_id", "relations"],
        ),
        "internal_contradictions": _array(
            {"claim_ids": {"type": "array", "items": _TEXT}, "explanation": _TEXT},
            ["claim_ids", "explanation"],
        ),
        "research_gaps": _array(
            {"objective_id": _TEXT, "explanation": _TEXT}, ["objective_id", "explanation"]
        ),
        "outdated_sources": _array(
            {"source_id": _TEXT, "explanation": _TEXT}, ["source_id", "explanation"]
        ),
    },
    "required": ["claims", "internal_contradictions", "research_gaps", "outdated_sources"],
}


# ------------------------------------------------------------------ request


def claims_to_verify(qc_input: QCInput, skip_claim_ids: set[str]) -> list[Claim]:
    """Fact-stating claims, except those the citation check already settled
    (fabricated or unverifiable citations)."""
    return [
        c
        for c in qc_input.lesson.claims
        if c.claim_type in EVIDENCE_REQUIRED and c.claim_id not in skip_claim_ids
    ]


def build_request(qc_input: QCInput, to_verify: list[Claim], today: date) -> dict:
    lesson, research = qc_input.lesson, qc_input.research
    cited = lesson.cited_source_ids()
    return {
        "today": today.isoformat(),
        "lesson_title": lesson.title,
        "learner_level": lesson.learner_level,
        "learning_objectives": [
            {"objective_id": o.id, "description": o.description}
            for o in lesson.learning_objectives
        ],
        "claims_to_verify": [
            {"claim_id": c.claim_id, "text": c.text, "claim_type": c.claim_type}
            for c in to_verify
        ],
        "lesson_claims": [
            {"claim_id": c.claim_id, "text": c.text}
            for c in lesson.claims
            if c.claim_type in EVIDENCE_REQUIRED | {ClaimType.MATHEMATICAL}
        ],
        "evidence_passages": [
            {"passage_id": p.passage_id, "source_id": s.source_id, "text": p.text}
            for s in research.sources
            if has_usable_evidence(s)
            for p in s.evidence_passages
        ],
        "cited_sources": [
            {
                "source_id": s.source_id,
                "title": s.title,
                "source_type": s.source_type,
                "published_at": s.published_at,
            }
            for s in research.sources
            if s.source_id in cited
        ],
    }


def make_validator(request: dict):
    """Reject any answer that skips a claim or invents an ID."""
    wanted = [c["claim_id"] for c in request["claims_to_verify"]]
    passages = {p["passage_id"] for p in request["evidence_passages"]}
    lesson_claims = {c["claim_id"] for c in request["lesson_claims"]}
    objectives = {o["objective_id"] for o in request["learning_objectives"]}
    sources = {s["source_id"] for s in request["cited_sources"]}

    def validate(review: QC1Review) -> None:
        problems = []
        answered = [c.claim_id for c in review.claims]
        if sorted(answered) != sorted(wanted):
            problems.append(f"'claims' must contain each of {wanted} exactly once, got {answered}")
        for c in review.claims:
            ids = [r.passage_id for r in c.relations]
            if len(ids) != len(set(ids)):
                problems.append(f"{c.claim_id}: a passage is listed twice")
            problems += [f"{c.claim_id}: unknown passage {p}" for p in ids if p not in passages]
        for x in review.internal_contradictions:
            problems += [f"unknown claim {i} in contradiction" for i in x.claim_ids if i not in lesson_claims]
        problems += [f"unknown objective {g.objective_id}" for g in review.research_gaps
                     if g.objective_id not in objectives]
        problems += [f"unknown or uncited source {o.source_id}" for o in review.outdated_sources
                     if o.source_id not in sources]
        if problems:
            raise LLMInvalidOutputError("; ".join(problems))

    return validate


# ----------------------------------------------------- relations -> verdicts


def _refs(qc_input: QCInput, passage_ids: list[str]) -> list[EvidenceRef]:
    owner = {
        p.passage_id: s.source_id
        for s in qc_input.research.sources
        for p in s.evidence_passages
    }
    return [EvidenceRef(source_id=owner[p], passage_id=p) for p in passage_ids]


def apply_claim_relations(
    qc_input: QCInput, claim: Claim, relations: list[PassageRelation], issues: IssueCollector
) -> ClaimAssessment:
    cited_sources = set(claim.source_ids)
    source_of = {
        p.passage_id: s.source_id for s in qc_input.research.sources for p in s.evidence_passages
    }

    def pick(relation: str, *, cited: bool | None = None) -> list[PassageRelation]:
        return [
            r
            for r in relations
            if r.relation == relation
            and (cited is None or (source_of[r.passage_id] in cited_sources) == cited)
        ]

    contradicting = pick("contradicts")
    supporting_cited = pick("supports", cited=True)
    partial_cited = pick("partially_supports", cited=True)
    supporting_other = pick("supports", cited=False)
    partial_other = pick("partially_supports", cited=False)

    def assessment(verdict: ClaimVerdict, used: list[PassageRelation], why: str) -> ClaimAssessment:
        return ClaimAssessment(
            claim_id=claim.claim_id,
            verdict=verdict,
            evidence=_refs(qc_input, [r.passage_id for r in used]),
            explanation=why,
        )

    def report(issue_type: IssueType, verdict: ClaimVerdict | None, used: list[PassageRelation],
               text: str, fix: str) -> None:
        issues.add(
            issue_type,
            text,
            section_id=claim.section_id,
            claim_id=claim.claim_id,
            claim_verdict=verdict,
            evidence=_refs(qc_input, [r.passage_id for r in used]),
            recommendation=fix,
        )

    if contradicting:
        why = f"Claim {claim.claim_id} is contradicted by the evidence: {contradicting[0].reason}"
        report(IssueType.CONTRADICTED_CLAIM, ClaimVerdict.CONTRADICTED, contradicting, why,
               "Rewrite the claim so it agrees with the evidence, or remove it.")
        return assessment(ClaimVerdict.CONTRADICTED, contradicting, why)

    if supporting_cited:
        why = f"Claim {claim.claim_id} is supported: {supporting_cited[0].reason}"
        return assessment(ClaimVerdict.SUPPORTED, supporting_cited, why)

    if partial_cited:
        why = f"Claim {claim.claim_id} is only partly supported: {partial_cited[0].reason}"
        report(IssueType.PARTIALLY_SUPPORTED_CLAIM, ClaimVerdict.PARTIALLY_SUPPORTED, partial_cited,
               why, "Narrow the claim to what the evidence states, or add evidence for the rest.")
        return assessment(ClaimVerdict.PARTIALLY_SUPPORTED, partial_cited, why)

    if supporting_other:
        if claim.source_ids:
            cited = ", ".join(claim.source_ids)
            better = ", ".join(sorted({source_of[r.passage_id] for r in supporting_other}))
            report(
                IssueType.MISLEADING_CITATION, None, supporting_other,
                f"Claim {claim.claim_id} cites {cited}, which does not support it; "
                f"the supporting evidence is in {better}.",
                f"Cite {better} instead of {cited}.",
            )
        why = f"Claim {claim.claim_id} is supported by uncited evidence: {supporting_other[0].reason}"
        return assessment(ClaimVerdict.SUPPORTED, supporting_other, why)

    if partial_other:
        why = f"Claim {claim.claim_id} is only partly supported, and not by its cited sources: " \
              f"{partial_other[0].reason}"
        report(IssueType.PARTIALLY_SUPPORTED_CLAIM, ClaimVerdict.PARTIALLY_SUPPORTED, partial_other,
               why, "Narrow the claim to what the evidence states and cite that source.")
        return assessment(ClaimVerdict.PARTIALLY_SUPPORTED, partial_other, why)

    why = f"No evidence passage supports claim {claim.claim_id}."
    report(IssueType.UNSUPPORTED_CLAIM, ClaimVerdict.UNSUPPORTED, [], why,
           "Find evidence for this claim or remove it.")
    return assessment(ClaimVerdict.UNSUPPORTED, [], why)


# ---------------------------------------------------------------------- run


def run_qc1_llm_review(
    qc_input: QCInput,
    issues: IssueCollector,
    client: LLMClient,
    *,
    skip_claim_ids: set[str],
    today: date,
) -> tuple[list[ClaimAssessment], str]:
    """Returns the claim assessments and the prompt version used."""
    prompt = load_prompt(PROMPT_PATH)
    to_verify = claims_to_verify(qc_input, skip_claim_ids)
    request = build_request(qc_input, to_verify, today)
    review = call_structured(
        client,
        system=prompt.text,
        user="INPUT:\n" + to_prompt_json(request),
        schema=RESPONSE_SCHEMA,
        output_model=QC1Review,
        validate=make_validator(request),
    )

    by_claim = {c.claim_id: c.relations for c in review.claims}
    assessments = [
        apply_claim_relations(qc_input, claim, by_claim[claim.claim_id], issues)
        for claim in to_verify
    ]
    for x in review.internal_contradictions:
        issues.add(
            IssueType.INTERNAL_CONTRADICTION,
            f"Claims {', '.join(x.claim_ids)} contradict each other: {x.explanation}",
            claim_id=x.claim_ids[0],
            recommendation="Make the claims consistent with each other and with the evidence.",
        )
    for g in review.research_gaps:
        issues.add(
            IssueType.RESEARCH_GAP,
            f"Objective {g.objective_id} is not covered by the research: {g.explanation}",
            objective_id=g.objective_id,
            recommendation="Run additional research for this objective.",
        )
    for o in review.outdated_sources:
        issues.add(
            IssueType.OUTDATED_SOURCE,
            f"{o.source_id} may be outdated for this topic: {o.explanation}",
            evidence=[EvidenceRef(source_id=o.source_id)],
            recommendation="Replace it with a current source.",
        )
    return assessments, prompt.version
