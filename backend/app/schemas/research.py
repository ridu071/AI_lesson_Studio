"""The research package (workflow section 5.5).

This is the evidence that QC1 checks lesson claims against. It is kept
separate from the generated lesson text (database rule 3).
"""

from datetime import date

from pydantic import Field, HttpUrl, model_validator

from app.schemas.common import (
    ContractModel,
    NonEmptyStr,
    PassageId,
    RequestId,
    SourceId,
    find_duplicates,
)
from app.schemas.enums import AccessStatus, AuthorityCategory, ContentAccess, SourceType


class EvidencePassage(ContractModel):
    passage_id: PassageId
    text: NonEmptyStr
    location: str | None = None  # e.g. "Section 2", "p. 41", "transcript 03:10-04:05"


class ResearchSource(ContractModel):
    source_id: SourceId
    source_type: SourceType
    title: NonEmptyStr
    publisher: str | None = None
    author: str | None = None
    url: HttpUrl | None = None  # books may have no URL
    published_at: date | None = None
    retrieved_at: date
    access_status: AccessStatus
    content_access: ContentAccess
    authority_category: AuthorityCategory = AuthorityCategory.UNKNOWN
    relevance_score: float | None = Field(default=None, ge=0, le=100)
    evidence_passages: list[EvidencePassage] = []

    @model_validator(mode="after")
    def _check_consistency(self) -> "ResearchSource":
        if self.content_access is ContentAccess.METADATA_ONLY and self.evidence_passages:
            raise ValueError(
                f"{self.source_id}: a metadata-only source cannot have evidence "
                "passages, because its content was never read"
            )
        if self.published_at and self.published_at > self.retrieved_at:
            raise ValueError(f"{self.source_id}: published_at is after retrieved_at")
        return self


class ResearchPackage(ContractModel):
    request_id: RequestId | None = None
    sources: list[ResearchSource] = []
    # Honest notes about what research could NOT establish.
    limitations: list[NonEmptyStr] = []

    @model_validator(mode="after")
    def _check_unique_ids(self) -> "ResearchPackage":
        problems = [
            f"duplicate source id {d}" for d in find_duplicates(s.source_id for s in self.sources)
        ]
        passage_ids = (p.passage_id for s in self.sources for p in s.evidence_passages)
        problems += [f"duplicate passage id {d}" for d in find_duplicates(passage_ids)]
        if problems:
            raise ValueError("Research package is invalid: " + "; ".join(problems))
        return self

    def find_source(self, source_id: str) -> ResearchSource | None:
        return next((s for s in self.sources if s.source_id == source_id), None)

    def find_passage(self, passage_id: str) -> EvidencePassage | None:
        for source in self.sources:
            for passage in source.evidence_passages:
                if passage.passage_id == passage_id:
                    return passage
        return None
