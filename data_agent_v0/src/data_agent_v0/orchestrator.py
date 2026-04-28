"""L4 Orchestrator —— 难度路由 + Plan-Executor with Replan。

入口 `run(task)` 与 baseline 的 ReActAgent.run() 对齐返回 AgentRunResult，
方便复用 starter-kit 的 runner.写出兼容 trace.json。

Easy/Medium → flat CodeAct (max_steps=executor.flat_max_steps)
Hard/Extreme → Plan-Executor，连续 N 步同错触发 replan，5 次 replan 后 force_submit。
"""
from __future__ import annotations

import json
import re
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

        # 顺序：先开 REPL（拿 schema + knowledge）→ 难度路由调 LLM 算 shape(+plan) → 注入 REPL
        # 这样 shape extractor 能看到完整 schema/knowledge，避免列名歧义错。
        repl = TaskRepl(
            task.context_dir,
            preload_enabled=True,
            preload_max_csv_mb=self.config.preload.max_csv_size_mb,
            shape_spec=None,  # 稍后通过 repl.set_shape_spec() 注入
        )
        try:
            schema_summary = repl.preload_summary
            knowledge = repl.knowledge if self.config.preload.inject_knowledge_md else {}
            schema_text = _render_summary_short(schema_summary)
            knowledge_text = _render_knowledge_full(knowledge)

            difficulty = (task.difficulty or "").lower()
            initial_plan: list[Any] = []
            if difficulty in self.config.planner.enable_for:
                ot.routed_branch = "plan_executor"
                # 合一 LLM 调用：单次同时输出 shape_spec + plan
                shape_spec, initial_plan = self.planner.create_plan_with_shape(
                    question=task.question,
                    schema_summary_text=schema_text,
                    knowledge_text=knowledge_text,
                )
            else:
                ot.routed_branch = "flat"
                # 仅 shape：flat 路径不需要 plan
                shape_spec = extract_shape_spec(
                    task.question,
                    self.model,
                    knowledge_md=knowledge_text,
                    schema_summary_text=schema_text,
                )
            ot.shape_spec = shape_spec
            repl.set_shape_spec(shape_spec)

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

            if ot.routed_branch == "plan_executor":
                run_result = self._run_plan_executor(
                    task, executor, system_prompt, ot, initial_plan=initial_plan
                )
            else:
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
        *,
        initial_plan: list[Any],
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

        # Plan 由调用方（run()）通过合一 LLM 调用预先生成，这里直接使用。
        plan = initial_plan
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


def _render_knowledge_full(knowledge: dict[str, str], max_chars: int = 8000) -> str:
    """按 '\\n## ' 章节切分；超长时按整章节单位丢弃尾部章节。

    旧实现按 char 硬截到 1500 chars，砍掉了 73% 的 metric 定义 / 例子 SQL /
    歧义解决章节。新实现：
      - cap = 8000 chars（实际 knowledge.md p95 ≈ 6.6k，留 buffer）
      - 多文件按 dict 序保留，每文件独立切
      - 每文件按 '\\n## ' 切段，超 budget 时按段单位 drop tail（不 mid-sentence 截）
      - 单段 > budget 才硬截（边界 case）
    qwen-plus 32k context 完全装得下。
    """
    parts: list[str] = []
    used = 0
    for name, body in knowledge.items():
        if used >= max_chars:
            break
        body = body.strip()
        if not body:
            continue
        # 按 '\n## ' 切段（H2 标题）；保留首段（H1 + 引言）
        sections = re.split(r"(?=\n## )", body)
        kept: list[str] = []
        for sec in sections:
            sec = sec.strip()
            if not sec:
                continue
            sec_len = len(sec) + 2  # 段落分隔双换行
            if used + sec_len > max_chars:
                # 段太长才硬截，否则整段丢
                if not kept and sec_len < max_chars * 2:
                    truncated = sec[: max_chars - used - 20] + "\n... [truncated]"
                    kept.append(truncated)
                    used = max_chars
                break
            kept.append(sec)
            used += sec_len
        if kept:
            parts.append(f"### {name}\n\n" + "\n\n".join(kept))
    return "\n\n".join(parts) if parts else "(none)"
