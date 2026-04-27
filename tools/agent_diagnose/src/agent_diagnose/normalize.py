"""把 baseline 与 v0 的 step 字段差异归一成统一展示模型。

baseline step.observation = {"ok", "tool", "content"}（content 为 dict）
v0 step.observation       = {"ok", "event", "stdout", "stderr", "traceback", ...}

模板只读 DisplayStep，不再分支。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

_PYTHON_FENCE_RE = re.compile(r"```python\s*\n?(.*?)```", re.DOTALL)
_JSON_FENCE_RE = re.compile(r"```json\s*\n?(.*?)```", re.DOTALL)


@dataclass(frozen=True)
class DisplayStep:
    step_index: int
    action: str
    ok: bool
    raw_response: str
    code: str | None
    output: str | None  # stdout / textual content
    error: str | None  # stderr or traceback
    submitted: bool
    # raw kept as JSON-serializable dict for "show raw" toggle
    raw: dict[str, Any]


_CODEACT_AGENT_KINDS = {"v0", "baseline_v1"}


def normalize_step(step: dict[str, Any], agent_kind: str) -> DisplayStep:
    step_index = int(step.get("step_index", 0))
    action = str(step.get("action", ""))
    ok = bool(step.get("ok", False))
    raw_response = str(step.get("raw_response", ""))
    obs = step.get("observation") or {}

    if agent_kind in _CODEACT_AGENT_KINDS:
        code = _extract_python_block(raw_response) or step.get("action_input", {}).get("code")
        output = obs.get("stdout") or None
        # error 来源：stderr / traceback / 顶层 error
        error_parts = []
        if obs.get("stderr"):
            error_parts.append(str(obs["stderr"]).strip())
        if obs.get("traceback"):
            error_parts.append(str(obs["traceback"]).strip())
        if obs.get("error"):
            error_parts.append(str(obs["error"]).strip())
        error = "\n\n".join(p for p in error_parts if p) or None
        submitted = obs.get("event") == "submit"
    else:  # baseline
        code = step.get("action_input", {}).get("code")
        # baseline 'content' 是 tool 返回内容；纯文本展示
        content = obs.get("content")
        if isinstance(content, dict):
            output = json.dumps(content, ensure_ascii=False, indent=2, default=str)
        elif content is None:
            output = None
        else:
            output = str(content)
        error = obs.get("error") or None
        if error is not None and not isinstance(error, str):
            error = str(error)
        submitted = action == "answer"

    return DisplayStep(
        step_index=step_index,
        action=action,
        ok=ok,
        raw_response=raw_response,
        code=code if code else None,
        output=output if output else None,
        error=error if error else None,
        submitted=submitted,
        raw=step,
    )


def normalize_steps(trace: dict[str, Any], agent_kind: str) -> list[DisplayStep]:
    return [normalize_step(s, agent_kind) for s in trace.get("steps", [])]


def detect_agent_kind(trace: dict[str, Any]) -> str:
    """通过 trace 中是否存在 v0_meta 判定 agent_kind，作为兜底。

    baseline_v1 / v0 都会在 trace 顶层注入 v0_meta；这里统一归到 v0 family，
    显示层只关心 step 结构是否 CodeAct（execute_python）。
    """
    return "v0" if "v0_meta" in trace else "baseline"


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _extract_python_block(text: str) -> str | None:
    m = _PYTHON_FENCE_RE.search(text)
    if m:
        return m.group(1)
    return None
