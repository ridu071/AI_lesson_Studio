"""Builds the configured LLM client."""

from app.core.config import Settings
from app.llm.base import LLMClient, LLMConfigError
from app.llm.gemini import GeminiClient


def create_llm_client(settings: Settings) -> LLMClient:
    if not settings.llm_configured:
        raise LLMConfigError("LLM_API_KEY is not set in backend/.env")
    if not settings.llm_model:
        raise LLMConfigError("LLM_MODEL is not set in backend/.env")
    if settings.llm_provider == "gemini":
        return GeminiClient(
            api_key=settings.llm_api_key.get_secret_value(),
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
            min_interval_seconds=settings.llm_min_interval_seconds,
        )
    raise LLMConfigError(f"unsupported LLM provider: {settings.llm_provider}")
