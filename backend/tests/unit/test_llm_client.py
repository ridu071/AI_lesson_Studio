import json

import pytest
from pydantic import BaseModel

from app.llm.base import (
    LLMConfigError,
    LLMInvalidOutputError,
    LLMUnavailableError,
    call_structured,
)
from app.llm.gemini import GeminiClient
from app.llm.prompts import load_prompt

KEY = "test-key-123"


def gemini_response(text: str, finish: str = "STOP", thought: str | None = None) -> bytes:
    parts = ([{"text": thought, "thought": True}] if thought else []) + [{"text": text}]
    return json.dumps({"candidates": [{"content": {"parts": parts}, "finishReason": finish}]}).encode()


class Transport:
    """Plays back (status, body) responses, or raises exceptions, in order."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, url, body, headers, timeout):
        self.requests.append({"url": url, "body": json.loads(body), "headers": headers})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def client(transport, **kw):
    return GeminiClient(api_key=KEY, model="gemini-test", transport=transport,
                        sleep=lambda s: None, **kw)


def test_returns_parsed_json_and_skips_thought_parts():
    t = Transport((200, gemini_response('{"ok": true}', thought="thinking...")))
    assert client(t).generate_json(system="s", user="u", schema={"type": "object"}) == {"ok": True}
    sent = t.requests[0]["body"]
    assert sent["generationConfig"]["temperature"] == 0
    assert sent["generationConfig"]["responseMimeType"] == "application/json"
    assert sent["systemInstruction"]["parts"][0]["text"] == "s"


def test_key_goes_in_header_never_in_url_or_repr():
    t = Transport((200, gemini_response("{}")))
    c = client(t)
    c.generate_json(system="s", user="u", schema={})
    assert t.requests[0]["headers"]["x-goog-api-key"] == KEY
    assert KEY not in t.requests[0]["url"]
    assert KEY not in repr(c)


def test_retries_rate_limit_and_timeouts_then_succeeds():
    t = Transport((429, b"{}"), TimeoutError("slow"), (503, b"{}"), (200, gemini_response("{}")))
    assert client(t, max_retries=3).generate_json(system="s", user="u", schema={}) == {}
    assert len(t.requests) == 4


def test_gives_up_after_max_retries():
    t = Transport((503, b"{}"), (503, b"{}"))
    with pytest.raises(LLMUnavailableError, match="after 2 attempts"):
        client(t, max_retries=1).generate_json(system="s", user="u", schema={})


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_permanent_errors_are_not_retried(status):
    t = Transport((status, b'{"error": {"message": "bad"}}'))
    with pytest.raises(LLMConfigError):
        client(t, max_retries=3).generate_json(system="s", user="u", schema={})
    assert len(t.requests) == 1


def test_truncated_answer_is_invalid():
    t = Transport((200, gemini_response('{"a": 1}', finish="MAX_TOKENS")))
    with pytest.raises(LLMInvalidOutputError, match="MAX_TOKENS"):
        client(t).generate_json(system="s", user="u", schema={})


def test_non_json_answer_is_invalid():
    t = Transport((200, gemini_response("Sure! Here is the JSON")))
    with pytest.raises(LLMInvalidOutputError, match="invalid JSON"):
        client(t).generate_json(system="s", user="u", schema={})


def test_empty_key_is_rejected():
    with pytest.raises(LLMConfigError):
        GeminiClient(api_key="  ", model="m")


# --- structured output validation ---


class Answer(BaseModel):
    value: int


class Scripted:
    model = "scripted"

    def __init__(self, *answers):
        self.answers, self.prompts = list(answers), []

    def generate_json(self, *, system, user, schema):
        self.prompts.append(user)
        return self.answers.pop(0)


def test_invalid_answer_is_retried_with_the_reason():
    llm = Scripted({"value": "not a number"}, {"value": 3})
    assert call_structured(llm, system="s", user="u", schema={}, output_model=Answer).value == 3
    assert "rejected for this reason" in llm.prompts[1]


def test_semantic_validation_failure_is_retried():
    def must_be_positive(a):
        if a.value <= 0:
            raise LLMInvalidOutputError("value must be positive")

    llm = Scripted({"value": -1}, {"value": 5})
    out = call_structured(llm, system="s", user="u", schema={}, output_model=Answer,
                          validate=must_be_positive)
    assert out.value == 5
    assert "value must be positive" in llm.prompts[1]


def test_still_invalid_after_retry_raises():
    llm = Scripted({"value": "x"}, {"value": "y"})
    with pytest.raises(LLMInvalidOutputError, match="after 2 attempts"):
        call_structured(llm, system="s", user="u", schema={}, output_model=Answer)


# --- prompts ---


@pytest.mark.parametrize("path", ["qc1/llm_review.md", "qc2/llm_review.md"])
def test_prompts_load_with_a_version_and_injection_warning(path):
    prompt = load_prompt(path)
    assert prompt.version == "0.1.0"
    assert "Never follow instructions" in prompt.text
    assert not prompt.text.startswith("---")


def quota_error(retry_delay: str) -> bytes:
    return json.dumps({"error": {"status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded",
                                 "details": [{"retryDelay": retry_delay}]}}).encode()


def test_daily_quota_fails_fast_without_retrying():
    t = Transport((429, quota_error("79194s")))
    with pytest.raises(LLMUnavailableError, match="quota exhausted; resets in about 22.0 h"):
        client(t, max_retries=3).generate_json(system="s", user="u", schema={})
    assert len(t.requests) == 1


def test_short_rate_limit_is_still_retried():
    t = Transport((429, quota_error("3s")), (200, gemini_response("{}")))
    assert client(t, max_retries=3).generate_json(system="s", user="u", schema={}) == {}
    assert len(t.requests) == 2
