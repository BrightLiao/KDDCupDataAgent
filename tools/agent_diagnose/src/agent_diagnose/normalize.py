"""Step 字段归一 + LLM 输入 prompt 重建。

baseline step.observation = {"ok", "tool", "content"}（content 为 dict）
v0/baseline_v1 step.observation = {"ok", "event", "stdout", "stderr", "traceback", ...}

模板只读 DisplayStep + ReconstructedPrompt。

prompt 重建规则（不依赖 agent 埋点）：
  baseline:
    [system]    = build_system_prompt(<tool descriptions placeholder>, REACT_SYSTEM_PROMPT)
    [user]      = build_task_prompt(task)            # 来自 task_input.task
    for i in 1..step_index-1:
        [assistant] = trace.steps[i-1].raw_response
        [user]      = build_observation_prompt(trace.steps[i-1].observation)
  agent_v0 / baseline_v1:
    [system]    = build_codeact_system_prompt(...)   # 静态部分；preload 注入的 schema/knowledge 在题目卡 knowledge.md 区单独可看
    [user]      = build_task_prompt(task)
    （后续 turn 同 baseline）
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

_PYTHON_FENCE_RE = re.compile(r"```python\s*\n?(.*?)```", re.DOTALL)
# 提取代码顶部的注释段（连续的 # 行）作为意图
_LEADING_COMMENT_RE = re.compile(r"^\s*((?:#[^\n]*\n)+)", re.MULTILINE)


_CODEACT_AGENT_KINDS = {"agent_v0", "baseline_v1", "v0"}  # "v0" 兼容老路径


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReconstructedMessage:
    role: str  # "system" | "user" | "assistant"
    content: str
    label: str  # 显示用：'system' / 'user (task)' / 'assistant (step 1)' / 'user (obs 1)' / ...


@dataclass(frozen=True)
class DisplayStep:
    step_index: int
    action: str
    ok: bool
    submitted: bool

    # 五栏数据
    intent: str | None        # ① 这一步要做什么 — thought / 代码注释 / 启发式
    prompt_messages: list[ReconstructedMessage]  # ② 发给 LLM 的 messages（重建）
    thinking: str | None      # ③.1 LLM 输出中代码块外的文字
    raw_response: str         # ③.2 原始 LLM 输出（含 fence）
    code: str | None          # ④ 提取出的 python 代码
    output: str | None        # ⑤ stdout / 工具返回内容
    error: str | None         # ⑤ stderr / traceback

    # 体验
    elapsed_seconds: float | None  # 单步耗时（如可推断）
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StaticTaskRecord:
    """重建 prompt 用的最小 task 对象。属性签名要够 build_task_prompt 用。"""
    task_id: str
    difficulty: str
    question: str


@dataclass(frozen=True)
class PlannerCall:
    """一次独立的 Planner LLM 调用 —— 由 orchestrator._run_plan_executor 触发。

    trace.json 不存 planner 的 prompt / 完整 messages，只存最终 plan + replan_events。
    诊断层据此重建 prompt（schema_summary 在运行时注入，无法精确还原，标 placeholder）。"""
    kind: str            # "create_plan" | "replan"
    label: str           # UI: "Initial plan (before step 1)" / "Replan #2 (after step 7)"
    at_step: int         # 0 for initial, replan_event.at_step for replans
    prompt: str          # 重建的 user prompt（planner 只发 user，无 system）
    output_plan: list[dict[str, Any]]  # plan JSON（仅最终 plan 存在 trace）
    replan_event: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_agent_kind(trace: dict[str, Any]) -> str:
    """trace 顶层有 v0_meta 即 CodeAct 系；否则当作 baseline。"""
    if "v0_meta" in trace:
        return "agent_v0"
    return "baseline"


def normalize_step(step: dict[str, Any], agent_kind: str) -> DisplayStep:
    """单步归一（不重建 prompt）。保留给单测使用。"""
    return _normalize_one(
        step,
        agent_kind=agent_kind,
        step_position=0,
        all_prior_steps=[],
        trace={},
        task_input=None,
    )


def normalize_steps(
    trace: dict[str, Any],
    agent_kind: str,
    *,
    task_input: dict[str, Any] | None = None,
) -> list[DisplayStep]:
    out: list[DisplayStep] = []
    raw_steps = trace.get("steps") or []
    for i, step in enumerate(raw_steps):
        out.append(_normalize_one(
            step,
            agent_kind=agent_kind,
            step_position=i,
            all_prior_steps=raw_steps[:i],
            trace=trace,
            task_input=task_input,
        ))
    return out


# ---------------------------------------------------------------------------
# Per-step normalization
# ---------------------------------------------------------------------------

def _normalize_one(
    step: dict[str, Any],
    *,
    agent_kind: str,
    step_position: int,
    all_prior_steps: list[dict[str, Any]],
    trace: dict[str, Any],
    task_input: dict[str, Any] | None,
) -> DisplayStep:
    step_index = int(step.get("step_index", step_position + 1))
    action = str(step.get("action", ""))
    ok = bool(step.get("ok", False))
    raw_response = str(step.get("raw_response", ""))
    obs = step.get("observation") or {}

    code, output, error, submitted = _extract_action_io(step, raw_response, obs, agent_kind, action)

    thinking = _extract_thinking(raw_response, agent_kind)
    intent = _extract_intent(step, code or "", thinking, agent_kind)

    prompt_messages = _reconstruct_prompt(
        agent_kind=agent_kind,
        prior_steps=all_prior_steps,
        trace=trace,
        task_input=task_input,
    )

    elapsed = step.get("elapsed_seconds")
    elapsed_f = float(elapsed) if isinstance(elapsed, (int, float)) else None

    return DisplayStep(
        step_index=step_index,
        action=action,
        ok=ok,
        submitted=submitted,
        intent=intent,
        prompt_messages=prompt_messages,
        thinking=thinking,
        raw_response=raw_response,
        code=code,
        output=output,
        error=error,
        elapsed_seconds=elapsed_f,
        raw=step,
    )


def _extract_action_io(
    step: dict[str, Any],
    raw_response: str,
    obs: dict[str, Any],
    agent_kind: str,
    action: str,
) -> tuple[str | None, str | None, str | None, bool]:
    if agent_kind in _CODEACT_AGENT_KINDS:
        # 优先 raw_response 中的 fence（与原归一逻辑一致）；fallback 到 action_input.code
        code = None
        m = _PYTHON_FENCE_RE.search(raw_response)
        if m:
            code = m.group(1)
        if not code:
            code = (step.get("action_input") or {}).get("code")
        output = obs.get("stdout") or None
        err_parts: list[str] = []
        for k in ("stderr", "traceback", "error"):
            v = obs.get(k)
            if v:
                err_parts.append(str(v).strip())
        error = "\n\n".join(p for p in err_parts if p) or None
        submitted = obs.get("event") == "submit"
        return (
            code if code else None,
            output if output else None,
            error if error else None,
            submitted,
        )

    # baseline (ReAct JSON)
    code = (step.get("action_input") or {}).get("code")
    content = obs.get("content")
    if isinstance(content, dict):
        import json as _json
        output = _json.dumps(content, ensure_ascii=False, indent=2, default=str)
    elif content is None:
        output = None
    else:
        output = str(content)
    error = obs.get("error")
    if error is not None and not isinstance(error, str):
        error = str(error)
    submitted = action == "answer"
    return (
        code if code else None,
        output if output else None,
        error if error else None,
        submitted,
    )


# ---------------------------------------------------------------------------
# Thinking / intent extraction
# ---------------------------------------------------------------------------

def _extract_thinking(raw_response: str, agent_kind: str) -> str | None:
    """raw_response 中代码块前后的散文 + 代码块顶部连续 # 注释段。"""
    if not raw_response:
        return None

    parts: list[str] = []
    # 1. fence 前后的 prose
    fence_match = _PYTHON_FENCE_RE.search(raw_response)
    if fence_match:
        prose_before = raw_response[: fence_match.start()].strip()
        prose_after = raw_response[fence_match.end():].strip()
        if prose_before:
            parts.append(prose_before)
        # 2. 代码顶部 # 注释段（v0 思考常以注释形式贴在代码顶部）
        code = fence_match.group(1)
        m = _LEADING_COMMENT_RE.match(code)
        if m:
            comment_block = "\n".join(
                line.lstrip("# ").rstrip()
                for line in m.group(1).strip().splitlines()
            ).strip()
            if comment_block:
                parts.append(comment_block)
        if prose_after:
            parts.append(prose_after)
    else:
        # baseline JSON：raw_response 整体就是 JSON，没思考散文，留空
        if not raw_response.lstrip().startswith("{") and "```json" not in raw_response:
            parts.append(raw_response.strip())

    text = "\n\n".join(p for p in parts if p)
    return text or None


def _extract_intent(
    step: dict[str, Any],
    code: str,
    thinking: str | None,
    agent_kind: str,
) -> str | None:
    """① Intent 一句话：thought（baseline）→ thinking 首句 → 代码首注释 → 启发式（pd.read_csv 等）。"""
    thought = step.get("thought")
    if isinstance(thought, str) and thought.strip():
        return _first_sentence(thought.strip())

    if thinking:
        return _first_sentence(thinking)

    if code:
        # 代码首注释
        m = _LEADING_COMMENT_RE.match(code)
        if m:
            first = m.group(1).strip().splitlines()[0]
            return _first_sentence(first.lstrip("# ").strip())

        # 启发式：识别常见 pandas / sql 调用
        h = _heuristic_intent(code)
        if h:
            return h

    return None


def _first_sentence(text: str, max_chars: int = 200) -> str:
    text = text.strip()
    # 截到第一个句号 / 换行
    for sep in ("\n", ". ", "。"):
        idx = text.find(sep)
        if 0 < idx < max_chars:
            return text[:idx].rstrip(".。 ").strip() + ("…" if sep == "\n" and len(text) > idx + 1 else "")
    return text[:max_chars] + ("…" if len(text) > max_chars else "")


def _heuristic_intent(code: str) -> str | None:
    snippets = []
    if re.search(r"\bsubmit\s*\(", code):
        snippets.append("Submit final answer")
    if re.search(r"pd\.read_csv\(", code):
        snippets.append("Load CSV")
    if re.search(r"\.read_sql\(|sqlite3\.connect", code):
        snippets.append("Query SQLite")
    if re.search(r"\.groupby\(", code):
        snippets.append("Aggregate by group")
    if re.search(r"\.merge\(|\.join\(", code):
        snippets.append("Join tables")
    if re.search(r"\.sort_values\(", code):
        snippets.append("Sort")
    if re.search(r"Path\([\'\"]\.\.?[\'\"]\)\.iterdir|sorted\(p\.name", code):
        snippets.append("Explore directory")
    if not snippets:
        return None
    return " · ".join(snippets[:3])


# ---------------------------------------------------------------------------
# Prompt reconstruction
# ---------------------------------------------------------------------------

def _reconstruct_prompt(
    *,
    agent_kind: str,
    prior_steps: list[dict[str, Any]],
    trace: dict[str, Any],
    task_input: dict[str, Any] | None,
) -> list[ReconstructedMessage]:
    """重建该 step 发出去那一刻 messages 的样子。
    导入 agent 包内置 prompt builders；失败时降级返回单条占位 message。"""
    msgs: list[ReconstructedMessage] = []

    # ---- system + initial user ----
    try:
        if agent_kind == "baseline":
            from data_agent_baseline.agents.prompt import (
                REACT_SYSTEM_PROMPT,
                build_observation_prompt,
                build_system_prompt,
                build_task_prompt,
            )
            tool_descriptions_placeholder = (
                "[tool registry — runtime injected; see data_agent_baseline.tools.registry "
                "for the exhaustive list of tools the agent had access to]"
            )
            system_content = build_system_prompt(tool_descriptions_placeholder, REACT_SYSTEM_PROMPT)
            task = _make_task_record(trace, task_input)
            task_content = build_task_prompt(_TaskShim(task)) if task else "(task input unavailable)"
            obs_builder = build_observation_prompt
        elif agent_kind in _CODEACT_AGENT_KINDS:
            from data_agent_v0.prompts import (
                build_codeact_system_prompt,
                build_observation_prompt,
                build_task_prompt,
            )
            v0_meta = trace.get("v0_meta") or {}
            shape_spec = v0_meta.get("shape_spec")
            # preload schema_summary / knowledge 不在 trace 里；只给静态 + shape_spec。
            # 题目页 knowledge.md 区单独显示原文，避免遗失诊断信息。
            system_content = build_codeact_system_prompt(
                schema_summary=None,
                knowledge=None,
                shape_spec=shape_spec,
            )
            note = (
                "\n\n[note] 'Preloaded data schema' & 'Domain knowledge' sections "
                "were injected at runtime from the live REPL preload + knowledge.md; "
                "they're not stored in trace.json. See the knowledge.md panel above."
            )
            system_content = system_content + note
            task = _make_task_record(trace, task_input)
            task_content = build_task_prompt(_TaskShim(task)) if task else "(task input unavailable)"
            obs_builder = build_observation_prompt
        else:
            return [ReconstructedMessage(
                role="system",
                content=f"(unknown agent_kind: {agent_kind} — cannot reconstruct prompt)",
                label="system",
            )]
    except Exception as exc:  # noqa: BLE001
        return [ReconstructedMessage(
            role="system",
            content=f"(unable to reconstruct prompt — import error: {exc!r})",
            label="system",
        )]

    msgs.append(ReconstructedMessage(role="system", content=system_content, label="system"))
    msgs.append(ReconstructedMessage(role="user", content=task_content, label="user (task)"))

    # ---- Plan-Executor branch: 注入初始 plan 消息（参 orchestrator._format_plan_message）----
    v0_meta = trace.get("v0_meta") or {}
    is_plan_executor = (
        agent_kind in _CODEACT_AGENT_KINDS
        and v0_meta.get("routed_branch") == "plan_executor"
    )
    plan_steps = v0_meta.get("plan") or [] if is_plan_executor else []
    replan_events = v0_meta.get("replan_events") or [] if is_plan_executor else []
    if plan_steps:
        msgs.append(ReconstructedMessage(
            role="user",
            content=_format_plan_text(plan_steps),
            label="user (initial plan)",
        ))

    # ---- prior turns ----
    for i, ps in enumerate(prior_steps, start=1):
        raw = str(ps.get("raw_response", ""))
        msgs.append(ReconstructedMessage(
            role="assistant",
            content=raw,
            label=f"assistant (step {i})",
        ))
        try:
            obs_text = obs_builder(ps.get("observation") or {})
        except Exception as exc:  # noqa: BLE001
            obs_text = f"(observation render failed: {exc!r})"
        msgs.append(ReconstructedMessage(
            role="user",
            content=obs_text,
            label=f"user (obs {i})",
        ))
        # Replan event 在 step i 失败后注入下一轮 prompt（at_step == i 的事件在该步 obs 之后）
        for ev in replan_events:
            if int(ev.get("at_step") or 0) == i:
                msgs.append(ReconstructedMessage(
                    role="user",
                    content=(
                        f"Plan revised after consecutive `{ev.get('signature')}` failures "
                        f"(replan #{ev.get('replan_count')}). "
                        f"[note] trace.json 只保留最终 plan，历史 plan 已被覆盖。"
                    ),
                    label=f"user (replan @ step {ev.get('at_step')})",
                ))
    return msgs


def _format_plan_text(plan_steps: list[dict[str, Any]]) -> str:
    """复刻 orchestrator._format_plan_message 的格式（操作 dict 而非 PlanStep）。"""
    if not plan_steps:
        return "(no plan)"
    lines = ["Here is the plan to follow:"]
    for i, s in enumerate(plan_steps, 1):
        lines.append(f"{i}. {s.get('description', '')}")
        sc = s.get("success_criterion")
        if sc:
            lines.append(f"   Success: {sc}")
    lines.append(
        "\nExecute the plan one step at a time. Reply with one ```python code block per turn."
    )
    return "\n".join(lines)


def _make_task_record(
    trace: dict[str, Any],
    task_input: dict[str, Any] | None,
) -> StaticTaskRecord | None:
    if not task_input:
        return None
    task_dict = task_input.get("task") or {}
    tid = task_input.get("task_id") or trace.get("task_id") or task_dict.get("task_id") or ""
    return StaticTaskRecord(
        task_id=str(tid),
        difficulty=str(task_dict.get("difficulty", "")),
        question=str(task_dict.get("question", "")),
    )


class _TaskShim:
    """够 build_task_prompt 用（只访问 .task_id / .difficulty / .question）。"""
    def __init__(self, rec: StaticTaskRecord) -> None:
        self.task_id = rec.task_id
        self.difficulty = rec.difficulty
        self.question = rec.question


# ---------------------------------------------------------------------------
# Planner LLM call reconstruction
# ---------------------------------------------------------------------------

_RUNTIME_SCHEMA_PLACEHOLDER = (
    "[runtime-injected from REPL preload — not stored in trace.json. "
    "Compact form: 'df_<name> (rows): [cols...]', 'json_<name> (records, top_keys)', "
    "'conn_<name>: tables=[(name, rows), ...]'.]"
)


def extract_planner_calls(
    trace: dict[str, Any],
    task_input: dict[str, Any] | None,
) -> list[PlannerCall]:
    """从 trace 推出 planner 发生的 N+1 次 LLM 调用：1 initial + N replan。
    flat 路径或非 plan-executor branch 返回空列表。"""
    v0_meta = trace.get("v0_meta") or {}
    if v0_meta.get("routed_branch") != "plan_executor":
        return []
    plan = v0_meta.get("plan") or []
    if not plan:
        return []

    out: list[PlannerCall] = []
    out.append(PlannerCall(
        kind="create_plan",
        label="Initial plan (before step 1)",
        at_step=0,
        prompt=_render_planner_initial_prompt(trace, task_input),
        output_plan=plan,
    ))

    for ev in (v0_meta.get("replan_events") or []):
        out.append(PlannerCall(
            kind="replan",
            label=f"Replan #{ev.get('replan_count')} (after step {ev.get('at_step')})",
            at_step=int(ev.get("at_step") or 0),
            prompt=_render_planner_replan_prompt(trace, task_input, ev),
            output_plan=plan,  # trace 仅保留最终 plan
            replan_event=ev,
        ))
    return out


def _render_planner_initial_prompt(
    trace: dict[str, Any],
    task_input: dict[str, Any] | None,
) -> str:
    """重建 planner 初始 LLM 调用的 prompt。F1+F2 之后，plan_executor 路径走
    合一调用 _INITIAL_PLAN_AND_SHAPE_PROMPT（同时输出 shape+plan）；老 trace
    可能用旧 _INITIAL_PLAN_PROMPT。优先尝试新模板，缺失时降级到旧。
    """
    v0_meta = trace.get("v0_meta") or {}
    task = (task_input or {}).get("task") or {}
    question = str(task.get("question", "(unknown)")).strip()
    plan_len = len(v0_meta.get("plan") or [])
    max_steps = max(plan_len, 5)
    knowledge_md = (task_input or {}).get("knowledge_md") or ""
    # F2 cap 8000 与 orchestrator._render_knowledge_full 对齐
    knowledge_text = knowledge_md[:8000] if knowledge_md else "(none)"

    # 优先用合一模板（F1+F2 之后的真实 prompt）
    try:
        from data_agent_v0.planner import _INITIAL_PLAN_AND_SHAPE_PROMPT  # type: ignore
        return _INITIAL_PLAN_AND_SHAPE_PROMPT.format(
            max_steps=max_steps,
            question=question,
            schema_summary=_RUNTIME_SCHEMA_PLACEHOLDER,
            knowledge=knowledge_text,
        )
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001
        return f"(planner merged module unavailable: {exc!r})"

    # 老路径：分离调用的 _INITIAL_PLAN_PROMPT，需要 shape_spec 占位
    try:
        from data_agent_v0.planner import _INITIAL_PLAN_PROMPT
    except Exception as exc:  # noqa: BLE001
        return f"(planner module not importable: {exc!r})"
    shape_spec = v0_meta.get("shape_spec")
    return _INITIAL_PLAN_PROMPT.format(
        max_steps=max_steps,
        question=question,
        schema_summary=_RUNTIME_SCHEMA_PLACEHOLDER,
        knowledge=knowledge_text,
        shape_spec=json.dumps(shape_spec, ensure_ascii=False) if shape_spec else "(no spec)",
    )


def _render_planner_replan_prompt(
    trace: dict[str, Any],
    task_input: dict[str, Any] | None,
    replan_event: dict[str, Any],
) -> str:
    try:
        from data_agent_v0.planner import _REPLAN_PROMPT
    except Exception as exc:  # noqa: BLE001
        return f"(planner module not importable: {exc!r})"

    v0_meta = trace.get("v0_meta") or {}
    task = (task_input or {}).get("task") or {}
    question = str(task.get("question", "(unknown)")).strip()
    sig = str(replan_event.get("signature", "(unknown)"))
    plan_len = len(v0_meta.get("plan") or [])
    max_steps = max(plan_len, 5)

    # recent_observations: replan 触发时取 at_step 之前最近 3 步的 observation
    at = int(replan_event.get("at_step") or 0)
    steps = trace.get("steps") or []
    obs_window = [s.get("observation") or {} for s in steps[:at]][-3:]
    obs_text = json.dumps(obs_window, ensure_ascii=False, indent=2, default=str)[:2000]

    remaining_plan = (
        "(remaining plan at replan point is not stored in trace.json — "
        "orchestrator overwrites v0_meta.plan with each replan. "
        "Only the *final* plan is shown in the output card below.)"
    )

    return _REPLAN_PROMPT.format(
        max_steps=max_steps,
        question=question,
        schema_summary=_RUNTIME_SCHEMA_PLACEHOLDER,
        failure_signature=sig,
        recent_observations=obs_text,
        remaining_plan=remaining_plan,
    )
