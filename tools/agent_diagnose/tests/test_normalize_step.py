"""验证 normalize 在 baseline 与 v0 step 上输出统一字段。"""
from __future__ import annotations

from agent_diagnose.normalize import detect_agent_kind, normalize_step


def test_baseline_step_normalizes():
    step = {
        "step_index": 1,
        "thought": "explore",
        "action": "list_context",
        "action_input": {"max_depth": 3},
        "raw_response": '```json\n{"action":"list_context"}\n```',
        "observation": {"ok": True, "tool": "list_context", "content": {"entries": []}},
        "ok": True,
    }
    ds = normalize_step(step, "baseline")
    assert ds.step_index == 1
    assert ds.action == "list_context"
    assert ds.ok is True
    assert ds.code is None  # list_context 没 code
    assert ds.output is not None and "entries" in ds.output
    assert ds.error is None
    assert ds.submitted is False


def test_baseline_answer_step_marks_submitted():
    step = {
        "step_index": 5,
        "action": "answer",
        "action_input": {"columns": ["x"], "rows": [["1"]]},
        "raw_response": "...",
        "observation": {"ok": True, "tool": "answer", "content": {"status": "submitted"}},
        "ok": True,
    }
    ds = normalize_step(step, "baseline")
    assert ds.submitted is True


def test_v0_step_extracts_code_from_fenced_block():
    step = {
        "step_index": 2,
        "action": "execute_python",
        "action_input": {"code": "print(1)"},
        "raw_response": "explanation\n```python\nprint(json_Patient)\n```\nthat's it",
        "observation": {"ok": True, "event": "ok", "stdout": "{...}\n"},
        "ok": True,
    }
    ds = normalize_step(step, "v0")
    assert ds.code is not None
    assert "print(json_Patient)" in ds.code
    assert ds.output is not None and "{...}" in ds.output
    assert ds.error is None
    assert ds.submitted is False


def test_v0_error_step_has_traceback():
    step = {
        "step_index": 3,
        "action": "execute_python",
        "raw_response": "```python\n1/0\n```",
        "observation": {
            "ok": False,
            "event": "error",
            "stdout": "",
            "stderr": "",
            "traceback": "Traceback (most recent call last):\nZeroDivisionError",
        },
        "ok": False,
    }
    ds = normalize_step(step, "v0")
    assert ds.ok is False
    assert ds.error is not None and "ZeroDivisionError" in ds.error


def test_v0_submit_event():
    step = {
        "step_index": 4,
        "action": "execute_python",
        "raw_response": "```python\nsubmit(df)\n```",
        "observation": {"ok": True, "event": "submit", "stdout": ""},
        "ok": True,
    }
    ds = normalize_step(step, "v0")
    assert ds.submitted is True


def test_detect_agent_kind():
    assert detect_agent_kind({"steps": [], "v0_meta": {}}) == "v0"
    assert detect_agent_kind({"steps": []}) == "baseline"
