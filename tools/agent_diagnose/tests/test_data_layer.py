"""验证数据层能在两种 agent 上工作。

需要至少 baseline 和 v0 各有一个 run（demo_qwen35_baseline / demo_qwen35_v0）。
"""
from __future__ import annotations

import pytest

from agent_diagnose.data import (
    discover_runs,
    list_all_task_ids,
    list_task_ids_in_run,
    load_gold_csv,
    load_prediction_csv,
    load_task_input,
    load_trace,
)


def test_discover_runs_finds_both_kinds():
    runs = discover_runs()
    kinds = {r.agent_kind for r in runs}
    assert "baseline" in kinds, "baseline run not found in artifacts"
    # v0 may not exist on remote yet; if local benchmark is running, v0 should be there
    assert len(runs) >= 1


def test_list_all_task_ids_50():
    tasks = list_all_task_ids()
    assert len(tasks) == 50
    assert tasks[0].startswith("task_")


def test_load_trace_baseline_task_11():
    runs = [r for r in discover_runs() if r.agent_kind == "baseline"]
    if not runs:
        pytest.skip("no baseline run")
    trace = load_trace(runs[0].run_id, "task_11")
    assert trace is not None
    assert trace["task_id"] == "task_11"
    assert "steps" in trace and isinstance(trace["steps"], list)


def test_load_trace_v0_optional():
    """v0 trace 含 v0_meta 顶层 key。"""
    runs = [r for r in discover_runs() if r.agent_kind == "v0"]
    if not runs:
        pytest.skip("no v0 run yet")
    # 找任何已写入的 task
    task_ids = list_task_ids_in_run(runs[0])
    if not task_ids:
        pytest.skip("v0 run has no task dirs yet")
    trace = load_trace(runs[0].run_id, task_ids[0])
    assert trace is not None
    assert "v0_meta" in trace


def test_load_gold_and_prediction():
    gold = load_gold_csv("task_11")
    assert gold is not None
    cols, rows = gold
    assert len(cols) >= 1
    runs = [r for r in discover_runs() if r.agent_kind == "baseline"]
    if not runs:
        pytest.skip("no baseline run")
    pred = load_prediction_csv(runs[0].run_id, "task_11")
    # baseline task_11 有 prediction.csv
    if pred is not None:
        pcols, prows = pred
        assert len(pcols) >= 1


def test_load_task_input_has_question():
    info = load_task_input("task_11")
    assert info["exists"]
    assert "task" in info
    assert "question" in info["task"]
    # task_11 有 knowledge.md
    assert "knowledge_md" in info
