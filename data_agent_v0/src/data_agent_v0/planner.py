"""L4 Planner —— 给 Hard/Extreme 题生成 plan，失败时 replan。

不在 v0 首版做的：LLM-judge 自适应 plan 长度、Tree-of-Plans 分支搜索。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from data_agent_baseline.agents.model import ModelAdapter, ModelMessage

_PLAN_FENCE_RE = re.compile(r"```json\s*\n?(.*?)```", re.DOTALL)


@dataclass(frozen=True, slots=True)
class PlanStep:
    description: str
    success_criterion: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"description": self.description, "success_criterion": self.success_criterion}


_INITIAL_PLAN_PROMPT = """
You are planning a multi-step data analysis. The execution will run in a CodeAct REPL
with all data already preloaded (DataFrames as `df_<name>`, JSON as `json_<name>`,
sqlite connections as `conn_<name>`).

Output a numbered plan of {max_steps} or fewer steps. Each step must be:
- Concrete enough to translate into one Python code block
- Phrased as an action ("compute X", "filter Y to Z", "join A and B on C")
- Avoid pure exploration steps — schema is already known

Output exactly one ```json fenced block containing a JSON list of objects with fields
`description` (string) and `success_criterion` (string, ≤1 sentence on what observable
output proves the step succeeded). No other text.

## Question
{question}

## Schema summary
{schema_summary}

## Domain knowledge
{knowledge}

## Expected answer shape
{shape_spec}
""".strip()


_REPLAN_PROMPT = """
The current plan stalled. You are revising the plan based on observed failures.

## Original question
{question}

## Schema summary
{schema_summary}

## What was tried so far (most recent step's failure signature)
{failure_signature}

## Recent observations (last 3 steps)
{recent_observations}

## Remaining steps (untried)
{remaining_plan}

Output a NEW plan (≤{max_steps} steps) that takes a different approach to reach the
answer. Use the same JSON format as the original plan: a ```json fenced block with a
list of objects with `description` and `success_criterion`. No other text.
""".strip()


class Planner:
    def __init__(self, model: ModelAdapter, max_steps: int = 5) -> None:
        self.model = model
        self.max_steps = max_steps

    def create_plan(
        self,
        *,
        question: str,
        schema_summary_text: str,
        knowledge_text: str,
        shape_spec: dict[str, Any] | None,
    ) -> list[PlanStep]:
        prompt = _INITIAL_PLAN_PROMPT.format(
            max_steps=self.max_steps,
            question=question.strip(),
            schema_summary=schema_summary_text or "(none)",
            knowledge=knowledge_text or "(none)",
            shape_spec=json.dumps(shape_spec, ensure_ascii=False) if shape_spec else "(no spec)",
        )
        raw = self.model.complete([ModelMessage(role="user", content=prompt)])
        return self._parse_plan(raw)

    def replan(
        self,
        *,
        question: str,
        schema_summary_text: str,
        failure_signature: str,
        recent_observations: list[dict[str, Any]],
        remaining_plan: list[PlanStep],
    ) -> list[PlanStep]:
        obs_text = json.dumps(
            recent_observations[-3:], ensure_ascii=False, indent=2, default=str
        )[:2000]
        remaining_text = (
            "\n".join(f"- {step.description}" for step in remaining_plan) or "(none)"
        )
        prompt = _REPLAN_PROMPT.format(
            max_steps=self.max_steps,
            question=question.strip(),
            schema_summary=schema_summary_text or "(none)",
            failure_signature=failure_signature,
            recent_observations=obs_text,
            remaining_plan=remaining_text,
        )
        raw = self.model.complete([ModelMessage(role="user", content=prompt)])
        return self._parse_plan(raw)

    # ------------------------------------------------------------------

    def _parse_plan(self, raw: str) -> list[PlanStep]:
        m = _PLAN_FENCE_RE.search(raw)
        text = m.group(1).strip() if m else raw.strip()
        try:
            payload = json.loads(text)
        except Exception:  # noqa: BLE001
            return []
        if not isinstance(payload, list):
            return []
        steps: list[PlanStep] = []
        for item in payload[: self.max_steps]:
            if not isinstance(item, dict):
                continue
            desc = str(item.get("description", "")).strip()
            if not desc:
                continue
            sc = str(item.get("success_criterion", "")).strip()
            steps.append(PlanStep(description=desc, success_criterion=sc))
        return steps
