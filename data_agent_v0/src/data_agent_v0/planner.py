"""L4 Planner —— 给 Hard/Extreme 题生成 plan，失败时 replan。

不在 v0 首版做的：LLM-judge 自适应 plan 长度、Tree-of-Plans 分支搜索。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from data_agent_baseline.agents.model import ModelAdapter, ModelMessage
from data_agent_v0.output.shape import _parse_shape_spec, _empty_spec

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
    # 合一调用：单次 LLM 同时输出 shape_spec + plan
    # ------------------------------------------------------------------

    def create_plan_with_shape(
        self,
        *,
        question: str,
        schema_summary_text: str,
        knowledge_text: str,
    ) -> tuple[dict[str, Any], list[PlanStep]]:
        """合一调用：plan_executor 路径上 shape extractor 与 planner 输入完全重叠
        （都是 question + 完整 knowledge + 完整 schema），分两次 LLM 调用纯属浪费。

        失败降级：JSON parse 失败 / 字段缺失 → spec 走 _empty_spec 路径，plan 返回 []。
        plan 为 [] 时 orchestrator 应退到无 plan 的 plain CodeAct（或直接走 flat 分支）。
        """
        prompt = _INITIAL_PLAN_AND_SHAPE_PROMPT.format(
            max_steps=self.max_steps,
            question=question.strip(),
            schema_summary=schema_summary_text or "(none)",
            knowledge=knowledge_text or "(none)",
        )
        try:
            raw = self.model.complete([ModelMessage(role="user", content=prompt)])
        except Exception as exc:  # noqa: BLE001
            return _empty_spec(error=f"llm_call_failed: {exc}"), []

        m = _PLAN_FENCE_RE.search(raw)
        text = m.group(1).strip() if m else raw.strip()
        try:
            payload = json.loads(text)
        except Exception as exc:  # noqa: BLE001
            return _empty_spec(error=f"json_parse_failed: {exc}", raw=raw[:200]), []

        if not isinstance(payload, dict):
            return _empty_spec(error="not_a_json_object", raw=raw[:200]), []

        shape_payload = payload.get("shape_spec") or {}
        plan_payload = payload.get("plan") or []
        if not isinstance(shape_payload, dict):
            spec = _empty_spec(error="shape_spec_not_a_dict", raw=raw[:200])
        else:
            spec = _parse_shape_spec(shape_payload)
        plan_list = plan_payload if isinstance(plan_payload, list) else []
        plan = self._parse_plan_list(plan_list)
        return spec, plan

    # ------------------------------------------------------------------

    def _parse_plan(self, raw: str) -> list[PlanStep]:
        """旧风格：从 raw LLM 输出（含 fence）解析单一 plan list。"""
        m = _PLAN_FENCE_RE.search(raw)
        text = m.group(1).strip() if m else raw.strip()
        try:
            payload = json.loads(text)
        except Exception:  # noqa: BLE001
            return []
        if not isinstance(payload, list):
            return []
        return self._parse_plan_list(payload)

    def _parse_plan_list(self, payload: list[Any]) -> list[PlanStep]:
        """从已解析的 list[dict] 中规整为 list[PlanStep]。

        合一调用拿到的是大 JSON 对象的子字段，已是 list；旧调用先经 _parse_plan
        把 raw → list 后再走这里。两路共用同一字段类型校验。
        """
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


# ---------------------------------------------------------------------------
# 合一 prompt — shape 规则 + plan 规则在同一份输入下产出
# ---------------------------------------------------------------------------

_INITIAL_PLAN_AND_SHAPE_PROMPT = """
You are doing two things in one shot for a data-analysis task that runs in a CodeAct
REPL (data preloaded as `df_<name>` for CSV, `json_<name>` for JSON, `conn_<name>`
for SQLite).

(1) Parse the question's expected answer SHAPE — which columns and at-most row count
    the final answer should have.
(2) Generate a numbered plan ({max_steps} or fewer steps) for solving the question.

Output exactly one fenced ```json block containing one JSON object with this
structure (and nothing else):

{{
  "shape_spec": {{
    "expected_columns": [...] | null,
    "expected_row_count": N | null,
    "row_count_kind": "at_most" | "all_matching" | null,
    "notes": "..."
  }},
  "plan": [
    {{"description": "...", "success_criterion": "..."}},
    ...
  ]
}}

# Shape rules

- "expected_columns": list of short snake_case strings, ordered as the question asks.
  Use the actual schema field names (or close synonyms). DO NOT collapse multiple
  schema fields into a single semantic column:
    * Question says "full name" and schema has `first_name` + `last_name`
      → ["first_name", "last_name"]  (two columns, NOT one "full_name")
    * Question says "score" but schema field is named `goal` → ["goal"]
  When the Domain knowledge section provides exemplar SQL or example queries, the
  SELECT clause there is authoritative — match its column count and ordering literally.
  If ambiguous, output null.

  AVOID these common over-reaches:
    * Foreign-key fields: schema columns named `*_id`, `link_to_*`, `*_ref` are
      pointers, NOT answers. Question "what's X's major?" + schema has `link_to_major`
      (FK) → output ["major_name"] (target table's name field), NOT ["link_to_major"].
      The plan must follow the link to retrieve the human-readable value.
    * Implicit subjects from pronouns: "give their consumption" / "their height" —
      the pronoun "their" refers back to a filtered subject. Do NOT add a subject
      column like `customer_id` or `name` unless the question explicitly says
      "list X and their Y" or "for each X, the Y". Singular questions about a
      filtered group ask only for the metric.
    * Tally / count adverbs without explicit grouping: "tally the X" or "count the X"
      usually means return X values (as a multiset, duplicates indicate frequency),
      NOT (X, count) two-column aggregate. Only output `count` when the question
      explicitly says "for each X give its count" or "X with frequency".

- "expected_row_count": integer ONLY when the question explicitly states a numeric
  cap ("top 5", "the 3 largest", "first 10"). For phrases like "list all X" or
  "state the date when Y" → null. Singular English phrasing does NOT imply count=1.

- "row_count_kind": "at_most" (top-N phrasing) or "all_matching" (find all that match)
  or null. Never "exact".

- "notes": optional one-sentence rationale. Can be empty.

# Plan rules

- Each step concrete enough to translate into one Python code block.
- Phrased as an action: "compute X", "filter df_Y where Z = 'V'",
  "join A and B on A.id = B.aid", "groupby X aggregate sum(Y)".
- Avoid pure exploration steps — schema is already given below.
- "success_criterion": ≤1 sentence on what observable output (DataFrame shape,
  printed values, column names) proves the step succeeded.
- The final plan step must end with `submit(...)` to terminate the task.

# Question

{question}

# Schema summary

{schema_summary}

# Domain knowledge

{knowledge}
""".strip()
