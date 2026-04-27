"""baseline-v1 orchestrator —— 扁平 ReAct + L1 CodeAct + L2 preload + L3 shape spec.

与 data_agent_v0.orchestrator.Orchestrator 的差异：移除 planner / replan / 难度路由，
始终走 CodeActExecutor.run_flat()。trace.json 仍带 v0_meta(shape_spec/routed_branch)
字段以便复用 agent_diagnose 现有的展示与评测。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_agent_baseline.agents.model import ModelAdapter
from data_agent_baseline.agents.runtime import AgentRunResult
from data_agent_baseline.benchmark.schema import PublicTask

from data_agent_v0.executor import CodeActExecutor
from data_agent_v0.output.shape import extract_shape_spec
from data_agent_v0.prompts import build_codeact_system_prompt
from data_agent_v0.repl import TaskRepl

from data_agent_baseline_v1.config import BaselineV1AppConfig


@dataclass
class _OrchestratorTrace:
    """trace.json 的 v0_meta 区块；planner/replan_events 留空字段以兼容 diagnose UI。"""

    shape_spec: dict[str, Any] | None = None
    plan: list[dict[str, Any]] = field(default_factory=list)
    replan_events: list[dict[str, Any]] = field(default_factory=list)
    routed_branch: str = "flat"

    def to_dict(self) -> dict[str, Any]:
        return {
            "shape_spec": self.shape_spec,
            "plan": self.plan,
            "replan_events": self.replan_events,
            "routed_branch": self.routed_branch,
        }


class Orchestrator:
    def __init__(self, *, model: ModelAdapter, config: BaselineV1AppConfig) -> None:
        self.model = model
        self.config = config

    def run(self, task: PublicTask) -> tuple[AgentRunResult, _OrchestratorTrace]:
        ot = _OrchestratorTrace()

        # L3 shape spec —— REPL 打开前一次 LLM 调用
        shape_spec = extract_shape_spec(task.question, self.model)
        ot.shape_spec = shape_spec

        # L2 preload —— 持久 REPL + 注入 schema/knowledge/shape_spec
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

            max_steps = min(self.config.executor.flat_max_steps, self.config.agent.max_steps)
            run_result = executor.run_flat(
                task,
                system_prompt=system_prompt,
                max_steps=max_steps,
                max_consecutive_failures=self.config.executor.max_consecutive_failures,
            )
            return run_result, ot
        finally:
            repl.shutdown()
