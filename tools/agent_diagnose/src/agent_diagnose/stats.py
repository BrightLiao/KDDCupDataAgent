"""Run-level KPI 派生 + 任务级跨 run 比对。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent_diagnose.data import RunRef, load_trace
from agent_diagnose.scoring import score_run_lazy


@dataclass
class RunKPIs:
    run: RunRef
    n_tasks: int
    micro: float
    macro: float
    submission_rate: float
    error_step_rate: float
    avg_steps: float
    per_difficulty: dict[str, Any]
    scored: dict[str, Any]  # 原始 scored payload


def compute_run_kpis(run: RunRef) -> RunKPIs | None:
    scored = score_run_lazy(run)
    if scored is None:
        return None
    tasks = scored.get("tasks") or []
    n = len(tasks)
    submitted = sum(1 for t in tasks if t.get("has_prediction"))

    total_steps = 0
    error_steps = 0
    for t in tasks:
        tr = load_trace(run.run_id, t["task_id"])
        if not tr:
            continue
        for s in tr.get("steps", []):
            total_steps += 1
            action = s.get("action") or ""
            if action.startswith("__"):  # __error__ / __parse_retry__
                error_steps += 1
            elif not s.get("ok", True):
                error_steps += 1

    return RunKPIs(
        run=run,
        n_tasks=n,
        micro=float(scored.get("micro_mean_score", 0.0)),
        macro=float(scored.get("macro_mean_score", 0.0)),
        submission_rate=submitted / n if n else 0.0,
        error_step_rate=error_steps / total_steps if total_steps else 0.0,
        avg_steps=total_steps / n if n else 0.0,
        per_difficulty=scored.get("per_difficulty") or {},
        scored=scored,
    )


# ---------------------------------------------------------------------------
# Cross-run task table
# ---------------------------------------------------------------------------

def task_score_matrix(kpis_list: list[RunKPIs]) -> dict[str, dict[str, dict[str, Any]]]:
    """{task_id: {run_id: {score, recall, has_prediction, difficulty, ...}}}"""
    matrix: dict[str, dict[str, dict[str, Any]]] = {}
    for kpis in kpis_list:
        for t in kpis.scored.get("tasks") or []:
            matrix.setdefault(t["task_id"], {})[kpis.run.run_id] = t
    return matrix


def task_difficulty_map(kpis_list: list[RunKPIs]) -> dict[str, str]:
    """以任意 scored 中的 difficulty 字段为准（多 run 都应一致）。"""
    out: dict[str, str] = {}
    for kpis in kpis_list:
        for t in kpis.scored.get("tasks") or []:
            if t["task_id"] not in out:
                out[t["task_id"]] = t.get("difficulty") or ""
    return out


def pick_reference_and_challenger(
    kpis_list: list[RunKPIs],
) -> tuple[RunKPIs | None, RunKPIs | None]:
    """规则：最新 baseline 为 reference，最新非 baseline 为 challenger。"""
    baselines = [k for k in kpis_list if k.run.agent_kind == "baseline"]
    challengers = [k for k in kpis_list if k.run.agent_kind != "baseline"]
    return (baselines[0] if baselines else None, challengers[0] if challengers else None)


def filter_task_ids(
    all_task_ids: list[str],
    matrix: dict[str, dict[str, dict[str, Any]]],
    reference: RunKPIs | None,
    challenger: RunKPIs | None,
    mode: str,
) -> list[str]:
    """按筛选模式返回 task_id 子集。"""
    if mode == "all" or mode not in {"regressions", "improvements", "both_zero", "disagreements"}:
        return all_task_ids
    if reference is None or challenger is None:
        return all_task_ids

    ref_id = reference.run.run_id
    chg_id = challenger.run.run_id
    out: list[str] = []
    for tid in all_task_ids:
        cells = matrix.get(tid, {})
        ref_score = (cells.get(ref_id) or {}).get("score")
        chg_score = (cells.get(chg_id) or {}).get("score")
        if mode == "regressions" and ref_score is not None and chg_score is not None and ref_score > chg_score + 1e-6:
            out.append(tid)
        elif mode == "improvements" and ref_score is not None and chg_score is not None and chg_score > ref_score + 1e-6:
            out.append(tid)
        elif mode == "both_zero":
            scores = [c.get("score", 0) for c in cells.values()]
            if scores and all(s == 0 for s in scores):
                out.append(tid)
        elif mode == "disagreements":
            scores = [c.get("score") for c in cells.values() if c.get("score") is not None]
            if scores and (max(scores) - min(scores)) > 0.3:
                out.append(tid)
    return out


def score_cell_class(score: float | None, has_prediction: bool) -> str:
    if score is None:
        return "s-missing"
    if not has_prediction:
        return "s-missing"
    if score >= 0.999:
        return "s-perfect"
    if score > 0:
        return "s-partial"
    return "s-zero"
