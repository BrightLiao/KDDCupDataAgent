"""CodeAct flat executor —— L1 单循环。

供 L4 Plan-Executor 复用：`run_flat()` 走简单循环；`run_step()` 接受单步目标
描述，返回中间结果，不自己主动 submit。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from data_agent_baseline.agents.model import ModelAdapter, ModelMessage
from data_agent_baseline.agents.runtime import AgentRunResult, StepRecord
from data_agent_baseline.benchmark.schema import AnswerTable, PublicTask

from data_agent_v0.prompts import (
    build_observation_prompt,
    build_parse_retry_prompt,
    build_task_prompt,
)
from data_agent_v0.repl import ReplResult, TaskRepl

_PYTHON_FENCE_RE = re.compile(r"```python\s*\n?(.*?)```", re.DOTALL)


def parse_python_block(raw: str) -> tuple[str | None, str | None]:
    """提取首个 ```python ... ``` 代码块。返回 (code, error_msg)，互斥。"""
    m = _PYTHON_FENCE_RE.search(raw)
    if m is None:
        return None, build_parse_retry_prompt()
    code = m.group(1)
    if not code.strip():
        return None, build_parse_retry_prompt()
    return code, None


@dataclass(frozen=True, slots=True)
class StepResult:
    """单步执行结果（供 Plan-Executor 模式驱动 replan 决策）。"""

    step_index: int
    repl_event: str
    raw_response: str
    code: str | None
    parse_error: str | None
    repl_result: ReplResult | None
    record: StepRecord

    @property
    def submitted(self) -> bool:
        return self.repl_event == "submit"

    @property
    def parse_failed(self) -> bool:
        return self.parse_error is not None

    @property
    def errored(self) -> bool:
        return self.repl_event in ("error", "timeout", "fatal")

    @property
    def error_signature(self) -> str:
        """归一化错误特征，用于 replan 触发的 dedup 计数。"""
        if self.parse_error:
            return "parse_error"
        if self.repl_result and self.repl_event == "error":
            tb = self.repl_result.traceback or ""
            # 取最后一行的异常类型，如 "ValueError: ..."
            for line in reversed(tb.strip().splitlines()):
                if ":" in line and not line.startswith(" "):
                    return line.split(":")[0].strip()[:80]
            return "error"
        return self.repl_event


class CodeActExecutor:
    """flat CodeAct 循环 + Plan-Executor 单步驱动接口共享实现。"""

    def __init__(
        self,
        *,
        model: ModelAdapter,
        repl: TaskRepl,
        step_timeout_seconds: int = 60,
    ) -> None:
        self.model = model
        self.repl = repl
        self.step_timeout = step_timeout_seconds

    def run_flat(
        self,
        task: PublicTask,
        *,
        system_prompt: str,
        max_steps: int = 8,
        max_consecutive_failures: int = 3,
    ) -> AgentRunResult:
        """flat CodeAct loop with死循环止损 + force-submit best-effort.

        - 连续 N 步同 error_signature 失败 → 注入 hint，逼 LLM 换路径或提交
        - max_steps 用尽未 submit → 最后再调一次 LLM 强制让它 submit 当前最佳
        """
        messages: list[ModelMessage] = [
            ModelMessage(role="system", content=system_prompt),
            ModelMessage(role="user", content=build_task_prompt(task)),
        ]
        steps: list[StepRecord] = []
        answer: AnswerTable | None = None
        consecutive_failures = 0
        last_signature: str | None = None

        for step_index in range(1, max_steps + 1):
            step = self._run_one_turn(messages, step_index)
            steps.append(step.record)
            if step.submitted and step.repl_result and step.repl_result.submitted:
                payload = step.repl_result.submitted
                answer = AnswerTable(
                    columns=list(payload["columns"]),
                    rows=[list(r) for r in payload["rows"]],
                )
                break

            if step.errored or step.parse_failed:
                sig = step.error_signature
                if sig == last_signature:
                    consecutive_failures += 1
                else:
                    consecutive_failures = 1
                    last_signature = sig
                if consecutive_failures >= max_consecutive_failures:
                    messages.append(
                        ModelMessage(
                            role="user",
                            content=(
                                f"You've failed {consecutive_failures} times in a row with the same "
                                f"error signature `{sig}`. Try a different approach (different "
                                "function, different join keys, different filter), or call "
                                "`submit(...)` with your current best-effort answer."
                            ),
                        )
                    )
                    consecutive_failures = 0
                    last_signature = None
            else:
                consecutive_failures = 0
                last_signature = None

        # Force submit best-effort if budget exhausted without submission
        if answer is None:
            forced_answer, forced_step = self.force_submit_best_effort(messages, len(steps) + 1)
            if forced_step is not None:
                steps.append(forced_step)
            if forced_answer is not None:
                answer = forced_answer

        failure_reason = (
            None if answer is not None else "Agent did not call submit() within max_steps."
        )
        return AgentRunResult(
            task_id=task.task_id,
            answer=answer,
            steps=steps,
            failure_reason=failure_reason,
        )

    def force_submit_best_effort(
        self,
        messages: list[ModelMessage],
        next_step_index: int,
    ) -> tuple[AnswerTable | None, StepRecord | None]:
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
        result = self._run_one_turn(messages, next_step_index)
        if result.submitted and result.repl_result and result.repl_result.submitted:
            payload = result.repl_result.submitted
            answer = AnswerTable(
                columns=list(payload["columns"]),
                rows=[list(r) for r in payload["rows"]],
            )
            return answer, result.record
        return None, result.record

    def run_one_step(
        self,
        messages: list[ModelMessage],
        step_index: int,
    ) -> StepResult:
        """供 L4 Plan-Executor 调用。messages 由调用方维护，本方法只追加并执行一步。"""
        return self._run_one_turn(messages, step_index)

    # ------------------------------------------------------------------

    def _run_one_turn(self, messages: list[ModelMessage], step_index: int) -> StepResult:
        raw = self.model.complete(messages)
        code, parse_err = parse_python_block(raw)

        if code is None:
            messages.append(ModelMessage(role="assistant", content=raw))
            messages.append(ModelMessage(role="user", content=parse_err or ""))
            record = StepRecord(
                step_index=step_index,
                thought="",
                action="__parse_retry__",
                action_input={},
                raw_response=raw,
                observation={"ok": False, "error": parse_err},
                ok=False,
            )
            return StepResult(
                step_index=step_index,
                repl_event="parse_error",
                raw_response=raw,
                code=None,
                parse_error=parse_err,
                repl_result=None,
                record=record,
            )

        result = self.repl.execute(code, timeout=self.step_timeout)
        observation = result.to_obs_dict()
        messages.append(ModelMessage(role="assistant", content=raw))
        messages.append(ModelMessage(role="user", content=build_observation_prompt(observation)))

        record = StepRecord(
            step_index=step_index,
            thought="",
            action="execute_python",
            action_input={"code": code},
            raw_response=raw,
            observation=observation,
            ok=result.ok,
        )
        return StepResult(
            step_index=step_index,
            repl_event=result.event,
            raw_response=raw,
            code=code,
            parse_error=None,
            repl_result=result,
            record=record,
        )
