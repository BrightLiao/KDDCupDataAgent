"""KDD Cup 2026 Phase 1 评分器 — 列多重集匹配（忽略列名 + 行序）。

按 [比赛简介.md §6.5] 与 [方案调研综述.md §7.1]：
    Score = Recall − λ · (Extra Columns / Predicted Columns)
其中：
- 把每一列看作"值向量（multiset）"，column 之间不区分顺序、列名不参与比对
- 行序忽略
- 数字保留 2 位小数；空值统一空字符串；日期统一成 ISO `YYYY-MM-DD`
- 浮点对齐 tolerance：abs(a-b) < 1e-6

CLI:
    uv run python src/eval/scorer.py \\
        --predict-root kddcup2026-starter-kit/artifacts/runs/demo_qwen35_baseline \\
        --gold-root data/demo/public/output \\
        --input-root data/demo/public/input \\
        --out reports/baseline_scored.json
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field, asdict
from pathlib import Path
from statistics import mean

DATE_PATTERNS = [
    re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    re.compile(r"^\d{4}/\d{1,2}/\d{1,2}$"),
    re.compile(r"^\d{4}\.\d{1,2}\.\d{1,2}$"),
]
ISO_DATE_RE = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[T ].*)?$")


def normalize_value(v) -> str:
    """归一化单值到字符串。规则按 §6.5 + §7.1。"""
    if v is None:
        return ""
    if isinstance(v, float):
        if math.isnan(v):
            return ""
        # 浮点保留 2 位小数（与 gold 对齐），但允许 1e-6 浮点抖动
        return f"{round(v, 2):.2f}".rstrip("0").rstrip(".") or "0"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, int):
        return str(v)
    s = str(v).strip()
    if s == "" or s.lower() in ("nan", "none", "null", "n/a"):
        return ""
    # 尝试数字
    try:
        x = float(s)
        if math.isnan(x):
            return ""
        if x == int(x) and "." not in s and "e" not in s.lower():
            return str(int(x))
        return f"{round(x, 2):.2f}".rstrip("0").rstrip(".") or "0"
    except ValueError:
        pass
    # 尝试日期
    m = ISO_DATE_RE.match(s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # 文本：去多余空格 + 大小写归一（multiset 字符串比对常见做法）
    return " ".join(s.split())


def read_csv_table(path: Path) -> tuple[list[str], list[list[str]]]:
    """读 CSV → (列名列表, 归一化后的行列表)"""
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return [], []
        rows = []
        for r in reader:
            # 行长度对齐 header（短的补空、长的截断）
            if len(r) < len(header):
                r = r + [""] * (len(header) - len(r))
            elif len(r) > len(header):
                r = r[: len(header)]
            rows.append([normalize_value(v) for v in r])
    return header, rows


def column_signature(rows: list[list[str]], col_idx: int) -> tuple:
    """把第 col_idx 列的所有值取出，按归一化字符串做 Counter，再转成可哈希的 multiset 签名。"""
    return tuple(sorted(Counter(row[col_idx] for row in rows).items()))


@dataclass
class TaskScore:
    task_id: str
    difficulty: str = ""
    has_prediction: bool = False
    pred_cols: int = 0
    gold_cols: int = 0
    matched: int = 0           # gold 列中有对应 pred 列的列数
    extra: int = 0             # pred 列里没匹配 gold 的列数（多余列）
    recall: float = 0.0        # matched / gold_cols
    extra_ratio: float = 0.0   # extra / max(pred_cols,1)
    score: float = 0.0         # recall - lam * extra_ratio
    note: str = ""


def score_task(pred_csv: Path, gold_csv: Path, lam: float = 0.5) -> TaskScore:
    ts = TaskScore(task_id=pred_csv.parent.name)
    if not pred_csv.is_file():
        ts.note = "no prediction.csv"
        return ts
    if not gold_csv.is_file():
        ts.note = "no gold.csv"
        return ts
    ts.has_prediction = True

    p_header, p_rows = read_csv_table(pred_csv)
    g_header, g_rows = read_csv_table(gold_csv)
    ts.pred_cols = len(p_header)
    ts.gold_cols = len(g_header)
    if not p_header or not g_header:
        ts.note = "empty header"
        return ts
    if not g_rows:
        ts.note = "empty gold rows"
        return ts

    # 计算每列签名（gold + pred）
    g_sigs = [column_signature(g_rows, i) for i in range(ts.gold_cols)]
    p_sigs = [column_signature(p_rows, i) for i in range(ts.pred_cols)]

    # 每个 pred 列只能匹配一个 gold 列（贪婪匹配，列签名相等即匹配）
    g_used = [False] * ts.gold_cols
    p_used = [False] * ts.pred_cols
    for pi, ps in enumerate(p_sigs):
        for gi, gs in enumerate(g_sigs):
            if not g_used[gi] and gs == ps:
                g_used[gi] = True
                p_used[pi] = True
                break
    ts.matched = sum(g_used)
    ts.extra = ts.pred_cols - sum(p_used)
    ts.recall = ts.matched / ts.gold_cols if ts.gold_cols else 0.0
    ts.extra_ratio = ts.extra / ts.pred_cols if ts.pred_cols else 0.0
    ts.score = max(0.0, ts.recall - lam * ts.extra_ratio)
    return ts


def score_batch(
    predict_root: Path,
    gold_root: Path,
    input_root: Path | None = None,
    lam: float = 0.5,
) -> dict:
    """对 <predict_root>/task_*/prediction.csv 全部评分，返回汇总。"""
    task_scores: list[TaskScore] = []
    for task_dir in sorted(predict_root.glob("task_*")):
        tid = task_dir.name
        pred_csv = task_dir / "prediction.csv"
        gold_csv = gold_root / tid / "gold.csv"
        ts = score_task(pred_csv, gold_csv, lam=lam)
        # difficulty
        if input_root is not None:
            tj = input_root / tid / "task.json"
            if tj.is_file():
                try:
                    ts.difficulty = json.loads(tj.read_text())["difficulty"]
                except Exception:
                    pass
        task_scores.append(ts)

    # 整体聚合
    n = len(task_scores)
    by_diff: dict[str, list[TaskScore]] = {}
    for ts in task_scores:
        by_diff.setdefault(ts.difficulty or "?", []).append(ts)

    micro = mean([t.score for t in task_scores]) if n else 0.0
    macro_means = {d: mean([t.score for t in ts]) for d, ts in by_diff.items()}
    macro = mean(macro_means.values()) if macro_means else 0.0

    return {
        "predict_root": str(predict_root),
        "gold_root": str(gold_root),
        "lam": lam,
        "n_tasks": n,
        "micro_mean_score": round(micro, 4),
        "macro_mean_score": round(macro, 4),
        "per_difficulty": {
            d: {
                "n": len(ts),
                "mean_score": round(mean([t.score for t in ts]), 4) if ts else 0.0,
                "n_perfect": sum(1 for t in ts if t.score >= 0.999),
                "n_zero": sum(1 for t in ts if t.score == 0.0),
            }
            for d, ts in by_diff.items()
        },
        "tasks": [asdict(t) for t in task_scores],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--predict-root", type=Path, required=True)
    ap.add_argument("--gold-root", type=Path, required=True)
    ap.add_argument("--input-root", type=Path, default=None)
    ap.add_argument("--lam", type=float, default=0.5)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    result = score_batch(args.predict_root, args.gold_root, args.input_root, lam=args.lam)
    print(f"\nTotal tasks: {result['n_tasks']}")
    print(f"Micro mean score: {result['micro_mean_score']}")
    print(f"Macro mean score: {result['macro_mean_score']}")
    print("\nPer-difficulty:")
    for d, s in sorted(result["per_difficulty"].items()):
        print(f"  {d:8s}  n={s['n']:3d}  mean={s['mean_score']:.4f}  perfect={s['n_perfect']}  zero={s['n_zero']}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"\nWritten {args.out}")


if __name__ == "__main__":
    main()
