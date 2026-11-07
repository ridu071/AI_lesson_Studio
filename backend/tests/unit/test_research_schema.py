import pytest
from pydantic import ValidationError

from app.schemas.research import ResearchPackage


def test_valid_fixture_loads(research_data):
    research = ResearchPackage.model_validate(research_data)
    assert len(research.sources) == 3
    assert research.find_source("SRC-002").title == "Machine Learning Concepts Guide"
    assert research.find_passage("EV-004") is not None
    assert research.find_source("SRC-999") is None


def test_duplicate_source_id_is_rejected(research_data):
    research_data["sources"][1]["source_id"] = "SRC-001"
    with pytest.raises(ValidationError, match="duplicate source id SRC-001"):
        ResearchPackage.model_validate(research_data)


def test_duplicate_passage_id_across_sources_is_rejected(research_data):
    research_data["sources"][1]["evidence_passages"][0]["passage_id"] = "EV-001"
    with pytest.raises(ValidationError, match="duplicate passage id EV-001"):
        ResearchPackage.model_validate(research_data)


def test_metadata_only_source_cannot_have_passages(research_data):
    # A video we only know the title of cannot supply evidence passages.
    research_data["sources"][2]["evidence_passages"] = [
        {"passage_id": "EV-100", "text": "Claimed quote from a video nobody watched."}
    ]
    with pytest.raises(ValidationError, match="metadata-only source cannot have evidence"):
        ResearchPackage.model_validate(research_data)


def test_published_after_retrieved_is_rejected(research_data):
    research_data["sources"][0]["published_at"] = "2027-01-01"
    with pytest.raises(ValidationError, match="published_at is after retrieved_at"):
        ResearchPackage.model_validate(research_data)


def test_relevance_score_above_100_is_rejected(research_data):
    research_data["sources"][0]["relevance_score"] = 140
    with pytest.raises(ValidationError):
        ResearchPackage.model_validate(research_data)
