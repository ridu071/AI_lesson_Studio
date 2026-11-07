import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Remove any real environment values so tests only see what they set."""
    for name in (
        "APP_ENV", "LLM_API_KEY", "LLM_MODEL", "MAX_LESSON_MINUTES",
        "QC1_MIN_SCORE", "QC2_MIN_SCORE", "RUBRIC_VERSION",
    ):
        monkeypatch.delenv(name, raising=False)


def make_settings(**overrides) -> Settings:
    # _env_file=None stops the test from reading your real backend/.env
    return Settings(_env_file=None, **overrides)


def test_defaults_match_project_rules():
    s = make_settings()
    assert s.max_lesson_minutes == 45
    assert s.app_env == "development"
    assert s.qc1_min_score == 80
    assert s.qc2_min_score == 80
    assert s.llm_configured is False


def test_environment_variable_overrides_default(monkeypatch):
    monkeypatch.setenv("MAX_LESSON_MINUTES", "30")
    assert make_settings().max_lesson_minutes == 30


def test_api_key_is_never_exposed_in_repr():
    s = make_settings(llm_api_key="super-secret-key-123")
    assert s.llm_configured is True
    assert "super-secret-key-123" not in repr(s)
    assert "super-secret-key-123" not in str(s)


def test_blank_api_key_counts_as_not_configured(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "   ")
    assert make_settings().llm_configured is False


def test_invalid_environment_name_is_rejected(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging-ish")
    with pytest.raises(ValidationError):
        make_settings()


def test_score_threshold_must_be_between_0_and_100(monkeypatch):
    monkeypatch.setenv("QC1_MIN_SCORE", "150")
    with pytest.raises(ValidationError):
        make_settings()
