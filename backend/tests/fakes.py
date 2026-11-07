"""A scripted stand-in for a real LLM, so QC logic is tested offline."""

import json
from collections.abc import Callable
from typing import Any

from app.modules.qc.qc1 import llm_review as qc1_review
from app.modules.qc.qc2 import llm_review as qc2_review

Answer = dict | Callable[[dict], dict]


def clean_qc1(request: dict) -> dict:
    """Every claim supported by the passage the fixture intends for it."""
    intended = {"CL-001": "EV-001", "CL-002": "EV-002", "CL-003": "EV-003",
                "CL-004": "EV-004", "CL-005": "EV-005"}
    return {
        "claims": [
            {"claim_id": c["claim_id"],
             "relations": [{"passage_id": intended[c["claim_id"]], "relation": "supports",
                            "reason": "The passage states this."}]
             if c["claim_id"] in intended else []}
            for c in request["claims_to_verify"]
        ],
        "internal_contradictions": [],
        "research_gaps": [],
        "outdated_sources": [],
    }


class FakeLLM:
    model = "fake-model"

    def __init__(self, qc1: Answer | list[Answer] = clean_qc1,
                 qc2: Answer | list[Answer] = None) -> None:
        self._answers = {
            id(qc1_review.RESPONSE_SCHEMA): qc1 if isinstance(qc1, list) else [qc1],
            id(qc2_review.RESPONSE_SCHEMA): (qc2 if isinstance(qc2, list) else [qc2 or {"issues": []}]),
        }
        self.calls: list[dict[str, Any]] = []

    def generate_json(self, *, system: str, user: str, schema: dict) -> Any:
        request = json.loads(user.split("INPUT:\n", 1)[1].split("\n\nYour previous answer", 1)[0])
        self.calls.append({"system": system, "user": user, "request": request, "schema": schema})
        answers = self._answers[id(schema)]
        answer = answers.pop(0) if len(answers) > 1 else answers[0]
        if isinstance(answer, Exception):
            raise answer
        return answer(request) if callable(answer) else answer
