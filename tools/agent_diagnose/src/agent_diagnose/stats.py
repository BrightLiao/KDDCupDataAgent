"""Run-level KPI 派生 + 任务级跨 run 比对 + agent-kind 五维聚合。"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from agent_diagnose.config import AGENT_KIND_CANONICAL, AGENT_KIND_ORDER
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
    """规则：reference 选 AGENT_KIND_ORDER 里出现最早的 kind 的最新 run；
    challenger 选 AGENT_KIND_ORDER 里出现最晚的 kind 的最新 run。两者不同 kind 才返回。"""
    if not kpis_list:
        return None, None
    by_kind: dict[str, list[RunKPIs]] = {}
    for k in kpis_list:
        by_kind.setdefault(k.run.agent_kind, []).append(k)
    ordered_kinds = [k for k in AGENT_KIND_ORDER if k in by_kind]
    if len(ordered_kinds) < 2:
        return None, None
    ref_kind = ordered_kinds[0]
    chg_kind = ordered_kinds[-1]
    return by_kind[ref_kind][0], by_kind[chg_kind][0]


def filter_task_ids(
    all_task_ids: list[str],
    matrix: dict[str, dict[str, dict[str, Any]]],
    reference: RunKPIs | None,
    challenger: RunKPIs | None,
    mode: str,
) -> list[str]:
    """按筛选模式返回 task_id 子集（run 级，保留兼容）。"""
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


# ---------------------------------------------------------------------------
# Kind-level matrix（按 agent_kind 聚合多 seed 均值）
# ---------------------------------------------------------------------------

def kind_score_matrix(
    kpis_list: list[RunKPIs],
) -> dict[str, dict[str, dict[str, Any]]]:
    """{task_id: {agent_kind: {mean_score, n_runs, n_with_pred, representative_run_id, has_prediction}}}

    representative_run_id：该 kind 下命中该 task 的"第一个" run（用于单元格点击跳转回放）。
    has_prediction：只要该 kind 任一 run 提交过即 True。
    mean_score：仅对有提交的 run 取均值；全部缺则为 None。
    """
    by_kind: dict[str, list[RunKPIs]] = {}
    for k in kpis_list:
        if not _is_canonical(k):
            continue  # 非 canonical run 不进矩阵聚合（保留在 run 表里）
        by_kind.setdefault(k.run.agent_kind, []).append(k)

    out: dict[str, dict[str, dict[str, Any]]] = {}
    for kind, members in by_kind.items():
        for kpi in members:
            for t in kpi.scored.get("tasks") or []:
                tid = t["task_id"]
                cell = out.setdefault(tid, {}).setdefault(kind, {
                    "_scores": [],
                    "n_with_pred": 0,
                    "representative_run_id": None,
                    "has_prediction": False,
                    "difficulty": t.get("difficulty") or "",
                })
                if t.get("has_prediction"):
                    cell["_scores"].append(float(t.get("score") or 0))
                    cell["n_with_pred"] += 1
                    cell["has_prediction"] = True
                if cell["representative_run_id"] is None:
                    cell["representative_run_id"] = kpi.run.run_id

    # finalize means in a separate pass
    for tid, kinds in out.items():
        for kind, cell in kinds.items():
            scores = cell.pop("_scores")
            cell["mean_score"] = (sum(scores) / len(scores)) if scores else None
            cell["n_runs"] = len(by_kind[kind])
    return out


def filter_task_ids_by_kind(
    all_task_ids: list[str],
    kind_matrix: dict[str, dict[str, dict[str, Any]]],
    ref_kind: str | None,
    chg_kind: str | None,
    mode: str,
) -> list[str]:
    """按筛选模式返回 task_id 子集（kind 级）。"""
    if mode == "all" or mode not in {"regressions", "improvements", "both_zero", "disagreements"}:
        return all_task_ids
    if not ref_kind or not chg_kind or ref_kind == chg_kind:
        return all_task_ids
    out: list[str] = []
    for tid in all_task_ids:
        cells = kind_matrix.get(tid, {})
        ref = (cells.get(ref_kind) or {}).get("mean_score")
        chg = (cells.get(chg_kind) or {}).get("mean_score")
        if mode == "regressions" and ref is not None and chg is not None and ref > chg + 1e-6:
            out.append(tid)
        elif mode == "improvements" and ref is not None and chg is not None and chg > ref + 1e-6:
            out.append(tid)
        elif mode == "both_zero":
            scores = [(c.get("mean_score") or 0) for c in cells.values() if c.get("has_prediction")]
            if scores and all(s == 0 for s in scores):
                out.append(tid)
        elif mode == "disagreements":
            scores = [c["mean_score"] for c in cells.values() if c.get("mean_score") is not None]
            if scores and (max(scores) - min(scores)) > 0.3:
                out.append(tid)
    return out


def pick_reference_and_challenger_kinds(
    agg_list: list["AggKPIs"],
) -> tuple[str | None, str | None]:
    """AGENT_KIND_ORDER 上的最早 kind = reference，最晚 kind = challenger。"""
    if len(agg_list) < 2:
        return None, None
    return agg_list[0].agent_kind, agg_list[-1].agent_kind


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


# ---------------------------------------------------------------------------
# Agent-kind level aggregation (五维卡)
# ---------------------------------------------------------------------------

@dataclass
class AggKPIs:
    agent_kind: str
    n_runs: int
    runs: list[RunRef] = field(default_factory=list)
    micro_mean: float = 0.0
    micro_std: float = 0.0
    macro_mean: float = 0.0
    macro_std: float = 0.0
    submission_rate_mean: float = 0.0
    error_step_rate_mean: float = 0.0
    avg_steps_mean: float = 0.0
    # {difficulty: mean_score}
    per_difficulty_mean: dict[str, float] = field(default_factory=dict)


def _mean_std(xs: list[float]) -> tuple[float, float]:
    if not xs:
        return 0.0, 0.0
    m = sum(xs) / len(xs)
    if len(xs) <= 1:
        return m, 0.0
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return m, math.sqrt(var)


def _is_canonical(kpi: RunKPIs) -> bool:
    """命中 AGENT_KIND_CANONICAL 的 substring 即 canonical（参与聚合）。
    kind 不在 dict 里的全部视为 canonical（默认全收）。"""
    pattern = AGENT_KIND_CANONICAL.get(kpi.run.agent_kind)
    if pattern is None:
        return True
    return pattern in kpi.run.run_id


def aggregate_by_agent_kind(kpis_list: list[RunKPIs]) -> list[AggKPIs]:
    """按 agent_kind 聚合多 seed run，返回按 AGENT_KIND_ORDER 排序的列表。

    AGENT_KIND_CANONICAL 决定每个 kind 下哪些 run 参与均值；run 表与 score
    矩阵单元格点击仍展示所有 run，但 5维卡 / 矩阵聚合 / Δ 列只用 canonical。
    """
    by_kind: dict[str, list[RunKPIs]] = {}
    for k in kpis_list:
        if not _is_canonical(k):
            continue
        by_kind.setdefault(k.run.agent_kind, []).append(k)

    agg_list: list[AggKPIs] = []
    for kind in AGENT_KIND_ORDER:
        if kind not in by_kind:
            continue
        members = by_kind[kind]
        micros = [m.micro for m in members]
        macros = [m.macro for m in members]
        sub_rates = [m.submission_rate for m in members]
        err_rates = [m.error_step_rate for m in members]
        avg_steps = [m.avg_steps for m in members]
        micro_mean, micro_std = _mean_std(micros)
        macro_mean, macro_std = _mean_std(macros)

        # difficulty mean: weighted by n_tasks per difficulty across runs
        diff_acc: dict[str, list[float]] = {}
        for m in members:
            for d, info in (m.per_difficulty or {}).items():
                if isinstance(info, dict) and "mean_score" in info:
                    diff_acc.setdefault(d, []).append(float(info["mean_score"]))
        per_diff_mean = {d: sum(v) / len(v) for d, v in diff_acc.items() if v}

        agg_list.append(AggKPIs(
            agent_kind=kind,
            n_runs=len(members),
            runs=[m.run for m in members],
            micro_mean=micro_mean,
            micro_std=micro_std,
            macro_mean=macro_mean,
            macro_std=macro_std,
            submission_rate_mean=sum(sub_rates) / len(sub_rates),
            error_step_rate_mean=sum(err_rates) / len(err_rates),
            avg_steps_mean=sum(avg_steps) / len(avg_steps),
            per_difficulty_mean=per_diff_mean,
        ))

    # any kind not in AGENT_KIND_ORDER (forward compat) — append at end
    for kind, members in by_kind.items():
        if kind not in AGENT_KIND_ORDER:
            micros = [m.micro for m in members]
            macros = [m.macro for m in members]
            mm, ms = _mean_std(micros)
            mm2, ms2 = _mean_std(macros)
            agg_list.append(AggKPIs(
                agent_kind=kind,
                n_runs=len(members),
                runs=[m.run for m in members],
                micro_mean=mm,
                micro_std=ms,
                macro_mean=mm2,
                macro_std=ms2,
                submission_rate_mean=sum(m.submission_rate for m in members) / len(members),
                error_step_rate_mean=sum(m.error_step_rate for m in members) / len(members),
                avg_steps_mean=sum(m.avg_steps for m in members) / len(members),
            ))
    return agg_list


def sort_kpis_by_kind(kpis_list: list[RunKPIs]) -> list[RunKPIs]:
    """按 (AGENT_KIND_ORDER index, run mtime desc) 排，未知 kind 最后。"""
    order_idx = {k: i for i, k in enumerate(AGENT_KIND_ORDER)}
    return sorted(
        kpis_list,
        key=lambda k: (
            order_idx.get(k.run.agent_kind, 9999),
            -k.run.runs_dir.stat().st_mtime if k.run.runs_dir.is_dir() else 0,
        ),
    )


def agent_kind_color_class(kind: str) -> str:
    """统一映射到 CSS class，颜色族在 style.css 里定义。
    baseline 系列蓝色族；agent_v* 系列紫色族。"""
    safe = kind.replace("_", "-")
    return f"kind-{safe}"
