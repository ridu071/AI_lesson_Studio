"""Deterministic citation checks (no LLM).

These answer "does the cited evidence exist and can it be read?". Whether the
evidence actually SUPPORTS a claim needs language understanding and is
checked by the claim verifier in Step 6.
"""

from collections.abc import Iterator

from app.modules.qc.enums import ClaimVerdict, IssueType
from app.modules.qc.issues import IssueCollector
from app.modules.qc.schemas import EvidenceRef
from app.schemas.enums import AccessStatus, ClaimType
from app.schemas.lesson import LessonVersion
from app.schemas.research import ResearchPackage, ResearchSource

# Claim types that state facts and therefore need a citation.
# MATHEMATICAL claims are verified by computation; opinions, hypothetical
# examples, instructions and exercises do not need sources.
EVIDENCE_REQUIRED = frozenset({ClaimType.FACTUAL, ClaimType.DEFINITION})


def has_usable_evidence(source: ResearchSource) -> bool:
    """True if we have read passages from this source and it is not known to be gone."""
    return bool(source.evidence_passages) and source.access_status is not AccessStatus.INACCESSIBLE


def _citation_sites(
    lesson: LessonVersion,
) -> Iterator[tuple[str, str | None, str | None, list[str]]]:
    """Every place a lesson cites sources: (label, section_id, claim_id, source_ids)."""
    for s in lesson.sections:
        yield f"Section {s.section_id}", s.section_id, None, s.source_ids
    for c in lesson.claims:
        yield f"Claim {c.claim_id}", c.section_id, c.claim_id, c.source_ids
    for v in lesson.videos:
        if v.source_id:
            yield f"Video {v.video_id}", v.section_id, None, [v.source_id]


def check_citations(
    lesson: LessonVersion, research: ResearchPackage, issues: IssueCollector
) -> None:
    known = {s.source_id: s for s in research.sources}

    # 1. Fabricated citations: a cited source that research never produced.
    for label, section_id, claim_id, source_ids in _citation_sites(lesson):
        for source_id in source_ids:
            if source_id not in known:
                issues.add(
                    IssueType.FABRICATED_CITATION,
                    f"{label} cites {source_id}, which does not exist in the research package.",
                    section_id=section_id,
                    claim_id=claim_id,
                    recommendation="Remove the citation, or replace it with a source "
                    "from the research package that supports the content.",
                )

    # 2. Inaccessible sources, reported once per cited source.
    for source_id in sorted(lesson.cited_source_ids()):
        source = known.get(source_id)
        if source and source.access_status is AccessStatus.INACCESSIBLE:
            issues.add(
                IssueType.INACCESSIBLE_SOURCE,
                f"{source_id} ('{source.title}') could not be reached when last "
                f"retrieved on {source.retrieved_at.isoformat()}.",
                evidence=[EvidenceRef(source_id=source_id)],
                recommendation="Re-fetch the source, or replace it with an accessible one.",
            )

    # 3. Claims that state facts must cite readable evidence.
    for claim in lesson.claims:
        if claim.claim_type not in EVIDENCE_REQUIRED:
            continue
        if not claim.source_ids:
            issues.add(
                IssueType.MISSING_CITATION,
                f"Claim {claim.claim_id} is a {claim.claim_type} claim but cites no source.",
                section_id=claim.section_id,
                claim_id=claim.claim_id,
                recommendation="Cite a source from the research package that supports "
                "this claim, or remove the claim.",
            )
            continue

        # Fabricated IDs are already reported above; judge only the real sources.
        existing = [known[sid] for sid in claim.source_ids if sid in known]
        if existing and not any(has_usable_evidence(s) for s in existing):
            ids = ", ".join(s.source_id for s in existing)
            issues.add(
                IssueType.UNVERIFIABLE_CLAIM,
                f"Claim {claim.claim_id} cites only sources whose content was never read "
                f"or cannot be reached ({ids}), so it cannot be verified.",
                requires_manual_review=True,
                section_id=claim.section_id,
                claim_id=claim.claim_id,
                claim_verdict=ClaimVerdict.UNVERIFIABLE,
                evidence=[EvidenceRef(source_id=s.source_id) for s in existing],
                recommendation="Find a readable source with a passage supporting this "
                "claim, or ask the instructor to verify it.",
            )
