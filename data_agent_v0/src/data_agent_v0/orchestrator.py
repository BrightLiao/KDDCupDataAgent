"""L4 Orchestrator —— 难度路由 + Plan-Executor with Replan。

入口 `run(task)` 与 baseline 的 ReActAgent.run() 对齐返回 AgentRunResult，
方便复用 starter-kit 的 runner.写出兼容 trace.json。

Easy/Medium → flat CodeAct (max_steps=executor.flat_max_steps)
Hard/Extreme → Plan-Executor，连续 N 步同错触发 replan，5 次 replan 后 force_submit。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from data_agent_baseline.agents.model import ModelAdapter, ModelMessage
from data_agent_baseline.agents.runtime import AgentRunResult, StepRecord
from data_agent_baseline.benchmark.schema import AnswerTable, PublicTask

from data_agent_v0.config import V0AppConfig
from data_agent_v0.executor import CodeActExecutor, StepResult
from data_agent_v0.output.shape import extract_shape_spec
from data_agent_v0.planner import Planner, PlanStep
from data_agent_v0.prompts import (
    build_codeact_system_prompt,
    build_observation_prompt,
    build_task_prompt,
)
from data_agent_v0.repl import TaskRepl


@dataclass
class _OrchestratorTrace:
    """Plan-Executor 模式的额外元数据，附加到 trace.json。"""

    shape_spec: dict[str, Any] | None = None
    plan: list[dict[str, Any]] = field(default_factory=list)
    replan_events: list[dict[str, Any]] = field(default_factory=list)
    routed_branch: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "shape_spec": self.shape_spec,
            "plan": self.plan,
            "replan_events": self.replan_events,
            "routed_branch": self.routed_branch,
        }


class Orchestrator:
    def __init__(self, *, model: ModelAdapter, config: V0AppConfig) -> None:
        self.model = model
        self.config = config
        self.planner = Planner(model, max_steps=config.planner.max_plan_steps)

    def run(self, task: PublicTask) -> tuple[AgentRunResult, _OrchestratorTrace]:
        ot = _OrchestratorTrace()

        # L3: extract shape spec via one LLM call before opening REPL
        shape_spec = extract_shape_spec(task.question, self.model)
        ot.shape_spec = shape_spec

        # Open REPL with preload + shape_spec
        repl = TaskRepl(
            task.context_dir,
            preload_enabled=True,
            preload_max_csv_mb=self.config.preload.max_csv_size_mb,
            shape_spec=shape_spec,
        )
        try:
            schema_summary = repl.preload_summary
            knowledge = repl.knowledge if self.config.preload.inject_knowledge_md else {}

            system_prompt = build_codeact_system_prompt(
                schema_summary=schema_summary,
                knowledge=knowledge,
                shape_spec=shape_spec,
            )

            executor = CodeActExecutor(
                model=self.model,
                repl=repl,
                step_timeout_seconds=self.config.executor.step_timeout_seconds,
            )

            difficulty = (task.difficulty or "").lower()
            if difficulty in self.config.planner.enable_for:
                ot.routed_branch = "plan_executor"
                run_result = self._run_plan_executor(task, executor, system_prompt, ot)
            else:
                ot.routed_branch = "flat"
                run_result = executor.run_flat(
                    task,
                    system_prompt=system_prompt,
                    max_steps=self.config.executor.flat_max_steps,
                    max_consecutive_failures=self.config.planner.max_consecutive_failures,
                )
            return run_result, ot
        finally:
            repl.shutdown()

    # ------------------------------------------------------------------

    def _run_plan_executor(
        self,
        task: PublicTask,
        executor: CodeActExecutor,
        system_prompt: str,
        ot: _OrchestratorTrace,
    ) -> AgentRunResult:
        cfg = self.config.planner
        agent_cfg_max = self.config.agent.max_steps  # global hard cap on total steps

        messages: list[ModelMessage] = [
            ModelMessage(role="system", content=system_prompt),
            ModelMessage(role="user", content=build_task_prompt(task)),
        ]
        steps: list[StepRecord] = []
        consecutive_failures = 0
        replan_count = 0
        last_signature: str | None = None
        global_step_index = 0
        recent_observations: list[dict[str, Any]] = []

        # Initial plan
        plan = self.planner.create_plan(
            question=task.question,
            schema_summary_text=_render_summary_short(executor.repl.preload_summary),
            knowledge_text=_render_knowledge_short(executor.repl.knowledge),
            shape_spec=ot.shape_spec,
        )
        ot.plan = [s.to_dict() for s in plan]
        if plan:
            messages.append(
                ModelMessage(
                    role="user",
                    content=_format_plan_message(plan),
                )
            )

        while global_step_index < agent_cfg_max:
            global_step_index += 1
            result: StepResult = executor.run_one_step(messages, global_step_index)
            steps.append(result.record)

            if result.submitted and result.repl_result and result.repl_result.submitted:
                payload = result.repl_result.submitted
                answer = AnswerTable(
                    columns=list(payload["columns"]),
                    rows=[list(r) for r in payload["rows"]],
                )
                return AgentRunResult(
                    task_id=task.task_id,
                    answer=answer,
                    steps=steps,
                    failure_reason=None,
                )

            recent_observations.append(result.record.observation)

            if result.errored or result.parse_failed:
                sig = result.error_signature
                if sig == last_signature:
                    consecutive_failures += 1
                else:
                    consecutive_failures = 1
                    last_signature = sig

                if consecutive_failures >= cfg.max_consecutive_failures:
                    replan_count += 1
                    ot.replan_events.append(
                        {
                            "at_step": global_step_index,
                            "signature": sig,
                            "replan_count": replan_count,
                        }
                    )

                    if replan_count >= cfg.max_replan_count:
                        forced = self._force_submit_best_effort(
                            task, executor, messages, global_step_index, steps
                        )
                        if forced is not None:
                            return forced
                        return AgentRunResult(
                            task_id=task.task_id,
                            answer=None,
                            steps=steps,
                            failure_reason=(
                                f"Plan-Executor exhausted {cfg.max_replan_count} replans "
                                f"and force-submit failed."
                            ),
                        )

                    new_plan = self.planner.replan(
                        question=task.question,
                        schema_summary_text=_render_summary_short(executor.repl.preload_summary),
                        failure_signature=sig,
                        recent_observations=recent_observations,
                        remaining_plan=plan,
                    )
                    if new_plan:
                        plan = new_plan
                        ot.plan = [s.to_dict() for s in plan]
                        messages.append(
                            ModelMessage(
                                role="user",
                                content=(
                                    f"Plan revised after {consecutive_failures} consecutive "
                                    f"`{sig}` failures. New plan:\n" + _format_plan_message(plan)
                                ),
                            )
                        )
                        consecutive_failures = 0
                        last_signature = None
            else:
                consecutive_failures = 0
                last_signature = None

        # Out of step budget without submit
        forced = self._force_submit_best_effort(task, executor, messages, global_step_index, steps)
        if forced is not None:
            return forced
        return AgentRunResult(
            task_id=task.task_id,
            answer=None,
            steps=steps,
            failure_reason=f"Plan-Executor reached step budget ({agent_cfg_max}) without submit.",
        )

    def _force_submit_best_effort(
        self,
        task: PublicTask,
        executor: CodeActExecutor,
        messages: list[ModelMessage],
        last_step_index: int,
        steps: list[StepRecord],
    ) -> AgentRunResult | None:
        """最后一搏：让 LLM 看完整历史后用一个代码块强制 submit。"""
        messages.append(
            ModelMessage(
                role="user",
                content=(
                    "Step budget is nearly exhausted. Reply with one ```python code block "
                    "that calls `submit(...)` with your best-effort answer based on the "
                    "evidence so far. Even an approximate answer is better than no submission. "
                    "Output only the code block."
                ),
            )
        )
        result = executor.run_one_step(messages, last_step_index + 1)
        steps.append(result.record)
        if result.submitted and result.repl_result and result.repl_result.submitted:
            payload = result.repl_result.submitted
            return AgentRunResult(
                task_id=task.task_id,
                answer=AnswerTable(
                    columns=list(payload["columns"]),
                    rows=[list(r) for r in payload["rows"]],
                ),
                steps=steps,
                failure_reason=None,
            )
        return None


# ---------------------------------------------------------------------------
# Internal: prompt helpers
# ---------------------------------------------------------------------------

def _format_plan_message(plan: list[PlanStep]) -> str:
    if not plan:
        return "(no plan)"
    lines = ["Here is the plan to follow:"]
    for i, step in enumerate(plan, 1):
        lines.append(f"{i}. {step.description}")
        if step.success_criterion:
            lines.append(f"   Success: {step.success_criterion}")
    lines.append("\nExecute the plan one step at a time. Reply with one ```python code block per turn.")
    return "\n".join(lines)


def _render_summary_short(summary: dict[str, Any]) -> str:
    """compact rendering for planner prompt (avoid blowing up token cost)."""
    parts: list[str] = []
    for kind in ("csv", "json", "db"):
        section = summary.get(kind) or {}
        for name, info in section.items():
            if kind == "csv" and info.get("loaded"):
                col_names = [c["name"] for c in info.get("columns", [])]
                parts.append(f"df_{name} ({info.get('rows', '?')} rows): {col_names}")
            elif kind == "json" and "records" in info:
                parts.append(f"json_{name} ({info['records']} records, keys={info.get('top_keys', [])[:5]})")
            elif kind == "db" and "tables" in info:
                tbls = [(t["name"], t.get("rows", "?")) for t in info["tables"]]
                parts.append(f"conn_{name}: tables={tbls}")
    return "\n".join(parts) if parts else "(empty)"


def _render_knowledge_short(knowledge: dict[str, str], max_chars: int = 1500) -> str:
    parts: list[str] = []
    used = 0
    for name, body in knowledge.items():
        snippet = body.strip()
        if used + len(snippet) > max_chars:
            snippet = snippet[: max_chars - used]
        parts.append(f"### {name}\n{snippet}")
        used += len(snippet)
        if used >= max_chars:
            break
    return "\n\n".join(parts) if parts else "(none)"
