import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    # Read from disk every time, so each test gets its own copy to modify.
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def lesson_data() -> dict:
    return _load("valid_lesson.json")


@pytest.fixture
def research_data() -> dict:
    return _load("valid_research.json")

