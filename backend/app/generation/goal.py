"""Suggests a learning goal from a topic, for learners unsure how to phrase one."""

from pydantic import Field

from app.llm.base import LLMClient, call_structured, to_prompt_json
from app.llm.prompts import load_prompt
from app.schemas.common import ContractModel

SCHEMA = {"type": "object", "properties": {"goal": {"type": "string"}}, "required": ["goal"]}


class SuggestedGoal(ContractModel):
    goal: str = Field(min_length=15, max_length=300)


def suggest_goal(topic: str, level: str, client: LLMClient) -> str:
    prompt = load_prompt("generation/goal.md")
    answer = call_structured(client, system=prompt.text,
                             user="INPUT:\n" + to_prompt_json({"topic": topic, "level": level}),
                             schema=SCHEMA, output_model=SuggestedGoal)
    return answer.goal.strip().strip('"')
