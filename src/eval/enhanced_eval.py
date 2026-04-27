"""Enhanced demo evaluator —— 实现 EVAL_PLAN_30D.md §1 五类指标。

输入：一个或多个 run_dir（多个时计算 consistency 指标）。
输出：eval_report.json，含
    1. accuracy（micro/macro/per-difficulty/by-data-kind）          —— 基础列多重集分数
    2. distribution（step/raw_response_chars/submit_attempts 分布） —— 副作用监测
    3. failure_clusters（关键词归类）                              —— 失败模式定性
    4. consistency（仅多 run 时；all-agree / majority / entropy）  —— 主决策来源
    5. submission（每题成功提交率）                                —— 配额信号

CLI:
    uv run python -m src.eval.enhanced_eval \\
        --runs kddcup2026-starter-kit/artifacts/runs/demo_qwen35_baseline \\
        --gold-root data/demo/public/output \\
        --input-root data/demo/public/input \\
        --version-id baseline \\
        --out reports/baseline_eval_report.json

多 run consistency：
    --runs <dir1> <dir2> <dir3>
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from statistics import mean, median
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.eval.scorer import column_signature, read_csv_table, score_task

# ---------------------------------------------------------------------------
# Failure clustering
# ---------------------------------------------------------------------------

# 关键词规则按优先级匹配（先匹配先归）。与 EVAL_PLAN §1.1 表对齐。
FAILURE_RULES: list[tuple[str, list[str]]] = [
    ("timeout", ["timed out", "timeout", "TimeoutError"]),
    ("parse_error", ["parse_retry", "did not contain", "code block"]),
    ("schema_misunderstanding", [
        "KeyError", "no such column", "has no attribute", "AttributeError",
        "column not found", "key not found",
    ]),
    ("csv_format_issue", [
        "CParserError", "ParserError", "tokenizing data", "EOF inside",
        "Error tokenizing", "expected", "unable to parse",
    ]),
    ("type_error", ["TypeError", "could not convert", "ValueError: invalid literal"]),
    ("memory_error", ["MemoryError", "Killed"]),
    ("api_error", ["APIError", "RateLimit", "InvalidRequest", "401", "429", "503"]),
    ("submit_format", ["AnswerTable", "shape spec", "Reject submit"]),
    ("aggregation_error", ["GroupBy", "aggregation", "groupby"]),
    ("sql_syntax", ["sqlite3", "OperationalError", "no such table", "near \""]),
    ("step_budget_exhausted", ["max_steps", "step budget", "did not call submit"]),
]


def classify_failure(failure_reason: str | None, last_traceback: str | None) -> str:
    """对单题失败原因做关键词归类。返回 cluster 名；无失败返回 ''。"""
    if not failure_reason and not last_traceback:
        return ""
    haystack = f"{failure_reason or ''}\n{last_traceback or ''}"
    for cluster, keywords in FAILURE_RULES:
        for kw in keywords:
            if kw.lower() in haystack.lower():
                return cluster
    return "other"


# ---------------------------------------------------------------------------
# Single-task observation extraction
# ---------------------------------------------------------------------------

def _extract_last_traceback(steps: list[dict]) -> str | None:
    """trace 中最后一个 errored step 的 traceback / error 文本。"""
    for step in reversed(steps):
        obs = step.get("observation") or {}
        if obs.get("ok") is False:
            tb = obs.get("traceback") or obs.get("stderr") or obs.get("error")
            if tb:
                return str(tb)[:4000]
    return None


def _count_submit_attempts(steps: list[dict]) -> int:
    """统计 trace 中 submit 调用次数（v0：observation.event=='submit'；baseline：action=='answer'）。"""
    n = 0
    for step in steps:
        action = step.get("action") or ""
        obs = step.get("observation") or {}
        if action == "answer":
            n += 1
        elif obs.get("event") == "submit":
            n += 1
    return n


def _raw_response_chars(steps: list[dict]) -> int:
    """所有 step 的 raw_response 字符总长度（粗略 token 代理：chars / 4）。"""
    return sum(len(step.get("raw_response") or "") for step in steps)


def _data_kind_of_task(input_root: Path, task_id: str) -> str:
    """按 context 文件类型分组：csv / json / db / mixed。"""
    ctx = input_root / task_id / "context"
    if not ctx.is_dir():
        return "?"
    has_csv = (ctx / "csv").is_dir()
    has_json = (ctx / "json").is_dir()
    has_db = (ctx / "db").is_dir()
    kinds = [k for k, present in [("csv", has_csv), ("json", has_json), ("db", has_db)] if present]
    if len(kinds) == 0:
        return "?"
    if len(kinds) == 1:
        return kinds[0]
    return "mixed"


def _answer_signature(pred_csv: Path) -> str | None:
    """把预测的列多重集签名拼接成 hashable 字符串，用于跨 run 对比。

    使用归一化值（read_csv_table 已经做了），列签名按字典序排序后 hash —— 与 scorer 的列匹配语义一致。
    """
    if not pred_csv.is_file():
        return None
    try:
        header, rows = read_csv_table(pred_csv)
    except Exception:
        return None
    if not header or not rows:
        return None
    sigs = sorted(repr(column_signature(rows, i)) for i in range(len(header)))
    return "|".join(sigs)[:8000]


# ---------------------------------------------------------------------------
# Per-run aggregation
# ---------------------------------------------------------------------------

def _difficulty_of(input_root: Path, task_id: str) -> str:
    tj = input_root / task_id / "task.json"
    if not tj.is_file():
        return "?"
    try:
        return json.loads(tj.read_text())["difficulty"]
    except Exception:
        return "?"


def evaluate_run(
    run_dir: Path,
    gold_root: Path,
    input_root: Path,
    *,
    lam: float = 0.5,
) -> dict:
    """对单 run 产出 per_task + 5 类指标的中间字典。"""
    per_task: list[dict] = []
    for task_dir in sorted(run_dir.glob("task_*")):
        tid = task_dir.name
        pred_csv = task_dir / "prediction.csv"
        gold_csv = gold_root / tid / "gold.csv"
        trace_path = task_dir / "trace.json"

        ts = score_task(pred_csv, gold_csv, lam=lam)
        ts.difficulty = _difficulty_of(input_root, tid)

        # trace 派生的工程指标
        steps_count = 0
        chars = 0
        submit_attempts = 0
        failure_reason: str | None = None
        last_tb: str | None = None
        if trace_path.is_file():
            try:
                trace = json.loads(trace_path.read_text())
                steps = trace.get("steps") or []
                steps_count = len(steps)
                chars = _raw_response_chars(steps)
                submit_attempts = _count_submit_attempts(steps)
                failure_reason = trace.get("failure_reason")
                last_tb = _extract_last_traceback(steps)
            except Exception as e:
                failure_reason = f"trace_parse_error: {e}"

        cluster = classify_failure(failure_reason, last_tb) if (
            failure_reason or ts.score == 0.0 or not ts.has_prediction
        ) else ""

        per_task.append({
            **asdict(ts),
            "data_kind": _data_kind_of_task(input_root, tid),
            "submitted": ts.has_prediction,
            "steps": steps_count,
            "raw_response_chars": chars,
            "approx_tokens": chars // 4,
            "submit_attempts": submit_attempts,
            "failure_reason": failure_reason,
            "failure_cluster": cluster,
            "answer_signature": _answer_signature(pred_csv),
        })
    return {"per_task": per_task}


# ---------------------------------------------------------------------------
# Cross-run consistency
# ---------------------------------------------------------------------------

def _entropy(counts: list[int]) -> float:
    """归一化香农熵（log base = N），N=1 返回 0。"""
    total = sum(counts)
    if total <= 0:
        return 0.0
    n = len(counts)
    if n <= 1:
        return 0.0
    h = 0.0
    for c in counts:
        if c > 0:
            p = c / total
            h -= p * math.log(p)
    return round(h / math.log(n), 4)


def consistency_block(per_task_per_run: list[list[dict]]) -> dict:
    """多 run 同 task 的答案签名一致性。"""
    if len(per_task_per_run) < 2:
        return {"runs_per_task": 1, "note": "single run, consistency not computed"}

    n_runs = len(per_task_per_run)
    # 按 task_id 聚合
    by_task: dict[str, list[str | None]] = {}
    for run_pt in per_task_per_run:
        for t in run_pt:
            by_task.setdefault(t["task_id"], []).append(t.get("answer_signature"))

    all_agree = 0
    majority_agree = 0
    entropies: list[float] = []
    for tid, sigs in by_task.items():
        present = [s for s in sigs if s]
        if len(present) < n_runs:
            # 至少一 run 没提交 → 不算 all-agree；majority 看剩下的
            counts = list(Counter(present).values()) if present else []
        else:
            counts = list(Counter(present).values())
        if counts:
            top = max(counts)
            if top == n_runs:
                all_agree += 1
            if top * 2 > n_runs:
                majority_agree += 1
            entropies.append(_entropy(counts))
        else:
            entropies.append(0.0)

    return {
        "runs_per_task": n_runs,
        "n_tasks": len(by_task),
        "all_agree_count": all_agree,
        "majority_agree_count": majority_agree,
        "answer_entropy_mean": round(mean(entropies), 4) if entropies else 0.0,
    }


# ---------------------------------------------------------------------------
# Top-level report builder
# ---------------------------------------------------------------------------

def _summarize_distribution(values: list[float], *, key: str) -> dict:
    if not values:
        return {key: 0.0}
    sv = sorted(values)
    n = len(sv)
    p50 = median(sv)
    p95 = sv[min(n - 1, int(0.95 * n))]
    p99 = sv[min(n - 1, int(0.99 * n))]
    return {
        "mean": round(mean(sv), 2),
        "p50": round(p50, 2),
        "p95": round(p95, 2),
        "p99": round(p99, 2),
        "max": round(max(sv), 2),
    }


def _aggregate_per_task(per_run: list[dict]) -> list[dict]:
    """N 个 run 同 task_id 的 per_task 字典 → 单一聚合 per_task 字典 (按 task_id)。

    每个字段策略：
    - score / steps / approx_tokens / raw_response_chars: 跨 run 平均
    - submit_attempts: 平均
    - submitted: 任一 run 提交即视为提交（保守乐观）
    - per_run_scores: 列表，便于诊断
    - failure_cluster: 多数 run 失败时取多数 cluster；全部成功则空
    - difficulty / data_kind: 取 first run（task 元数据，跨 run 不变）
    """
    by_task: dict[str, list[dict]] = {}
    for run in per_run:
        for t in run["per_task"]:
            by_task.setdefault(t["task_id"], []).append(t)

    out: list[dict] = []
    for tid in sorted(by_task.keys()):
        items = by_task[tid]
        first = items[0]
        scores = [t["score"] for t in items]
        clusters = [t["failure_cluster"] for t in items if t["failure_cluster"]]
        cluster_majority = ""
        if clusters and len(clusters) * 2 >= len(items):
            cluster_majority = Counter(clusters).most_common(1)[0][0]
        out.append({
            "task_id": tid,
            "difficulty": first.get("difficulty", "?"),
            "data_kind": first.get("data_kind", "?"),
            "score": round(mean(scores), 4),
            "score_min": round(min(scores), 4),
            "score_max": round(max(scores), 4),
            "per_run_scores": [round(s, 4) for s in scores],
            "submitted": any(t["submitted"] for t in items),
            "submit_rate_across_runs": round(sum(1 for t in items if t["submitted"]) / len(items), 4),
            "steps": round(mean([t["steps"] for t in items]), 2),
            "approx_tokens": round(mean([t["approx_tokens"] for t in items]), 2),
            "submit_attempts": round(mean([t["submit_attempts"] for t in items]), 2),
            "failure_cluster": cluster_majority,
            "failure_reasons": [t.get("failure_reason") for t in items if t.get("failure_reason")],
            "n_runs": len(items),
        })
    return out


def build_report(
    *,
    version_id: str,
    runs: list[Path],
    gold_root: Path,
    input_root: Path,
    lam: float = 0.5,
    git_commit: str = "",
) -> dict:
    """主入口：N 个 run 路径 → eval_report.json 字典。

    多 run 时所有指标按"跨 run 平均到 task 级别"再聚合，避免单 run 噪声主导。
    consistency block 单独看 answer_signature 一致性。
    """
    per_run = [evaluate_run(r, gold_root, input_root, lam=lam) for r in runs]
    n_runs = len(per_run)

    if n_runs == 1:
        agg_pt = per_run[0]["per_task"]
    else:
        agg_pt = _aggregate_per_task(per_run)

    n_tasks = len(agg_pt)

    # ---- accuracy ----
    by_diff: dict[str, list[dict]] = {}
    by_kind: dict[str, list[dict]] = {}
    for t in agg_pt:
        by_diff.setdefault(t.get("difficulty") or "?", []).append(t)
        by_kind.setdefault(t.get("data_kind") or "?", []).append(t)

    micro = mean([t["score"] for t in agg_pt]) if agg_pt else 0.0
    by_diff_means = {d: round(mean([t["score"] for t in lst]), 4) for d, lst in by_diff.items()}
    macro = round(mean(by_diff_means.values()), 4) if by_diff_means else 0.0

    accuracy = {
        "micro_mean_score": round(micro, 4),
        "macro_mean_score": macro,
        "by_difficulty": {
            d: {
                "n": len(lst),
                "mean_score": round(mean([t["score"] for t in lst]), 4),
                "n_perfect": sum(1 for t in lst if t["score"] >= 0.999),
                "n_zero": sum(1 for t in lst if t["score"] <= 1e-9),
            }
            for d, lst in by_diff.items()
        },
        "by_data_kind": {
            k: {
                "n": len(lst),
                "mean_score": round(mean([t["score"] for t in lst]), 4),
            }
            for k, lst in by_kind.items()
        },
    }

    # ---- distribution ----
    distribution = {
        "step_per_task": _summarize_distribution([t["steps"] for t in agg_pt], key="step_per_task"),
        "approx_tokens_per_task": _summarize_distribution(
            [t["approx_tokens"] for t in agg_pt], key="approx_tokens_per_task"
        ),
        "submit_attempts": {
            "once": sum(1 for t in agg_pt if 0.5 < t["submit_attempts"] <= 1.5),
            "multiple": sum(1 for t in agg_pt if t["submit_attempts"] > 1.5),
            "zero": sum(1 for t in agg_pt if t["submit_attempts"] <= 0.5),
        },
    }

    # ---- failure clusters ---- 多 run 取 task 多数 cluster
    cluster_counter: Counter = Counter()
    for t in agg_pt:
        if t["failure_cluster"]:
            cluster_counter[t["failure_cluster"]] += 1
    failure_clusters = dict(sorted(cluster_counter.items(), key=lambda kv: -kv[1]))

    # ---- submission ---- 多 run 时按 "任一 run 提交" 计
    submitted = sum(1 for t in agg_pt if t["submitted"])
    submission = {
        "submitted_count": submitted,
        "submission_rate": round(submitted / n_tasks, 4) if n_tasks else 0.0,
        "n_perfect": sum(1 for t in agg_pt if t["score"] >= 0.999),
        "n_zero": sum(1 for t in agg_pt if t["score"] <= 1e-9),
    }

    # ---- consistency ----
    consistency = consistency_block([pr["per_task"] for pr in per_run])

    return {
        "version_id": version_id,
        "git_commit": git_commit,
        "runs": [str(r) for r in runs],
        "gold_root": str(gold_root),
        "input_root": str(input_root),
        "lam": lam,
        "n_tasks": n_tasks,
        "n_runs": n_runs,
        "accuracy": accuracy,
        "distribution": distribution,
        "submission": submission,
        "failure_clusters": failure_clusters,
        "consistency": consistency,
        "tasks": agg_pt,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=Path, nargs="+", required=True, help="一个或多个 run_dir（多个 → consistency）")
    ap.add_argument("--gold-root", type=Path, required=True)
    ap.add_argument("--input-root", type=Path, required=True)
    ap.add_argument("--version-id", type=str, required=True, help="本次评测的版本标识，如 baseline / v0_v3")
    ap.add_argument("--git-commit", type=str, default="", help="可选：当前 git commit")
    ap.add_argument("--lam", type=float, default=0.5)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    report = build_report(
        version_id=args.version_id,
        runs=args.runs,
        gold_root=args.gold_root,
        input_root=args.input_root,
        lam=args.lam,
        git_commit=args.git_commit,
    )

    print(f"\n=== {args.version_id} ===")
    print(f"n_tasks: {report['n_tasks']}, runs={len(args.runs)}")
    print(f"micro: {report['accuracy']['micro_mean_score']}  macro: {report['accuracy']['macro_mean_score']}")
    print(f"submission_rate: {report['submission']['submission_rate']}  perfect: {report['submission']['n_perfect']}")
    print("by_difficulty:")
    for d, s in sorted(report["accuracy"]["by_difficulty"].items()):
        print(f"  {d:8s}  n={s['n']:3d}  mean={s['mean_score']:.4f}  perfect={s['n_perfect']}  zero={s['n_zero']}")
    print(f"step_per_task: {report['distribution']['step_per_task']}")
    print(f"approx_tokens_per_task: {report['distribution']['approx_tokens_per_task']}")
    print(f"submit_attempts: {report['distribution']['submit_attempts']}")
    print(f"failure_clusters: {report['failure_clusters']}")
    if report["consistency"].get("runs_per_task", 1) > 1:
        print(f"consistency: {report['consistency']}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"\nWritten {args.out}")


if __name__ == "__main__":
    main()
