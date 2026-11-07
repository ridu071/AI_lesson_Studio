"""The LLM interface, its errors, and the structured-output helper."""

import json
from collections.abc import Callable
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError


class LLMError(Exception):
    """Base class. Any LLMError means "the evaluation could not be completed":
    the audit becomes ERROR and is retried. It never counts against the lesson."""


class LLMConfigError(LLMError):
    """Missing key, unknown model, bad request: retrying will not help."""


class LLMUnavailableError(LLMError):
    """Timeouts, rate limits or server errors that persisted after all retries."""


class LLMInvalidOutputError(LLMError):
    """The model's answer was not valid JSON for the requested schema."""


class LLMClient(Protocol):
    model: str

    def generate_json(self, *, system: str, user: str, schema: dict[str, Any]) -> Any:
        """Return the model's answer parsed as JSON, constrained to `schema`."""
        ...


T = TypeVar("T", bound=BaseModel)


def call_structured(
    client: LLMClient,
    *,
    system: str,
    user: str,
    schema: dict[str, Any],
    output_model: type[T],
    validate: Callable[[T], None] | None = None,
    attempts: int = 2,
) -> T:
    """Ask for JSON, validate its shape (pydantic) and meaning (`validate`).

    On an invalid answer, ask again once, telling the model what was wrong.
    The model's output is never trusted until it passes both checks.
    """
    prompt = user
    last_error = ""
    for _ in range(attempts):
        raw = client.generate_json(system=system, user=prompt, schema=schema)
        try:
            parsed = output_model.model_validate(raw)
            if validate:
                validate(parsed)
            return parsed
        except (ValidationError, LLMInvalidOutputError, ValueError) as exc:
            last_error = str(exc)[:1500]
            prompt = (
                f"{user}\n\nYour previous answer was rejected for this reason:\n{last_error}\n"
                "Return a corrected answer that follows the rules and the schema exactly."
            )
    raise LLMInvalidOutputError(f"model output still invalid after {attempts} attempts: {last_error}")


def to_prompt_json(data: Any) -> str:
    """Serialise input data for a prompt (stable key order, readable)."""
    return json.dumps(data, indent=1, ensure_ascii=False, sort_keys=False, default=str)
