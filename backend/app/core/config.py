"""Central application settings.

Every configurable value lives here and is read from environment variables
(or from backend/.env during development). Secrets never appear in code.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> parents[2] is the "backend" folder.
# Anchoring the .env path here means it works no matter where you run Python from.
BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "testing", "production"] = "development"

    # Optional in Step 1. SecretStr hides the value in logs and print().
    llm_api_key: SecretStr | None = None
    llm_model: str | None = None

    # Hard rule: mandatory lesson content must fit in this many minutes.
    max_lesson_minutes: int = Field(default=45, ge=1, le=240)

    # Starting thresholds. Release eligibility also depends on hard rules,
    # so a high score alone can never make a lesson eligible.
    qc1_min_score: float = Field(default=80.0, ge=0, le=100)
    qc2_min_score: float = Field(default=80.0, ge=0, le=100)

    # The rubric version is NOT a setting: it lives next to the weights it
    # describes, in app/modules/qc/scoring/rubrics.py.

    @property
    def llm_configured(self) -> bool:
        return self.llm_api_key is not None and bool(
            self.llm_api_key.get_secret_value().strip()
        )


@lru_cache
def get_settings() -> Settings:
    """Load settings once and reuse them."""
    return Settings()
