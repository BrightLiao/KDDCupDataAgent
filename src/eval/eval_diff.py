"""自动 diff 报告 —— 对比两份 eval_report.json，输出 EVAL_PLAN_30D.md §1.3 风格 markdown。

视觉等级：
  🟢 强信号  consistency / failure_clusters 主因显著好转
  ⚠️ 副作用  分布尾部恶化（token p95 / step p95）
  🔴 红线    扰动鲁棒性退步、submission rate 下降、出现新 failure cluster
  🟡 噪声    accuracy ±差距 < 8%（50 条噪声范围）

CLI:
    uv run python -m src.eval.eval_diff \\
        --base reports/baseline_eval_report.json \\
        --challenger reports/v0_v3_eval_report.json \\
        --out reports/baseline_vs_v0_v3.md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


_NOISE_THRESHOLD = 0.08  # accuracy 差距 < 8% 视为噪声


def _fmt_pct(x: float) -> str:
    return f"{x*100:+.1f}%"


def _fmt_delta_int(a: int, b: int) -> str:
    return f"{a} → {b} ({b-a:+d})"


def _fmt_delta_float(a: float, b: float, *, digits: int = 4) -> str:
    return f"{a:.{digits}f} → {b:.{digits}f} ({b-a:+.{digits}f})"


def _icon_for_acc_delta(delta: float) -> str:
    if abs(delta) < _NOISE_THRESHOLD:
        return "🟡"
    return "🟢" if delta > 0 else "🔴"


def _icon_for_count_delta(delta: int, *, higher_is_better: bool = True) -> str:
    if delta == 0:
        return "🟡"
    good = (delta > 0) if higher_is_better else (delta < 0)
    return "🟢" if good else "🔴"


def _icon_for_dist_delta(a: float, b: float, *, ratio_threshold: float = 0.15) -> str:
    """分布尾部对比：增长 > 15% 视为副作用。"""
    if a <= 0:
        return "🟡"
    ratio = (b - a) / a
    if abs(ratio) < ratio_threshold:
        return "🟡"
    return "⚠️" if ratio > 0 else "🟢"  # 增加 = 副作用，减少 = 改善


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _section_header(base: dict, ch: dict) -> list[str]:
    return [
        f"# Eval diff — `{base['version_id']}` vs `{ch['version_id']}`",
        "",
        f"- runs: {len(base.get('runs', []))} vs {len(ch.get('runs', []))}",
        f"- n_tasks: {base['n_tasks']} vs {ch['n_tasks']}",
        f"- lam: {base.get('lam')} / {ch.get('lam')}",
        "",
    ]


def _section_consistency(base: dict, ch: dict) -> list[str]:
    bc = base.get("consistency") or {}
    cc = ch.get("consistency") or {}
    if bc.get("runs_per_task", 1) <= 1 and cc.get("runs_per_task", 1) <= 1:
        return []
    lines = ["## Consistency（主信号）", ""]
    if bc.get("runs_per_task", 1) <= 1 or cc.get("runs_per_task", 1) <= 1:
        lines.append("- ⚠️ 一方为单 run，无法对齐。建议两侧都跑 ≥ 2 seed。")
        lines.append("")
        return lines
    a_all = bc.get("all_agree_count", 0)
    b_all = cc.get("all_agree_count", 0)
    a_maj = bc.get("majority_agree_count", 0)
    b_maj = cc.get("majority_agree_count", 0)
    a_ent = bc.get("answer_entropy_mean", 0.0)
    b_ent = cc.get("answer_entropy_mean", 0.0)

    lines.append(f"- {_icon_for_count_delta(b_all - a_all)} all_agree: {_fmt_delta_int(a_all, b_all)}")
    lines.append(f"- {_icon_for_count_delta(b_maj - a_maj)} majority_agree: {_fmt_delta_int(a_maj, b_maj)}")
    lines.append(f"- {_icon_for_count_delta(int((a_ent - b_ent) * 1000))} answer_entropy: {_fmt_delta_float(a_ent, b_ent, digits=4)}（lower better）")
    lines.append("")
    return lines


def _section_accuracy(base: dict, ch: dict) -> list[str]:
    ba = base["accuracy"]
    ca = ch["accuracy"]
    micro_d = ca["micro_mean_score"] - ba["micro_mean_score"]
    macro_d = ca["macro_mean_score"] - ba["macro_mean_score"]
    icon_micro = _icon_for_acc_delta(micro_d)
    icon_macro = _icon_for_acc_delta(macro_d)

    lines = [
        "## Accuracy（辅助；50 条噪声 ±8% 视为噪声）",
        "",
        f"- {icon_micro} micro: {_fmt_delta_float(ba['micro_mean_score'], ca['micro_mean_score'])}",
        f"- {icon_macro} macro: {_fmt_delta_float(ba['macro_mean_score'], ca['macro_mean_score'])}",
        "",
        "### by_difficulty",
        "",
        "| difficulty | base mean | ch mean | Δ | base perfect / zero | ch perfect / zero |",
        "| --- | ---: | ---: | ---: | --- | --- |",
    ]
    diffs = sorted(set(ba["by_difficulty"]) | set(ca["by_difficulty"]))
    for d in diffs:
        b = ba["by_difficulty"].get(d, {"mean_score": 0.0, "n_perfect": 0, "n_zero": 0})
        c = ca["by_difficulty"].get(d, {"mean_score": 0.0, "n_perfect": 0, "n_zero": 0})
        delta = c["mean_score"] - b["mean_score"]
        lines.append(
            f"| {d} | {b['mean_score']:.4f} | {c['mean_score']:.4f} | {delta:+.4f} | "
            f"{b['n_perfect']} / {b['n_zero']} | {c['n_perfect']} / {c['n_zero']} |"
        )
    lines.append("")

    lines += [
        "### by_data_kind",
        "",
        "| kind | base mean | ch mean | Δ |",
        "| --- | ---: | ---: | ---: |",
    ]
    kinds = sorted(set(ba.get("by_data_kind", {})) | set(ca.get("by_data_kind", {})))
    for k in kinds:
        b = ba["by_data_kind"].get(k, {"mean_score": 0.0})
        c = ca["by_data_kind"].get(k, {"mean_score": 0.0})
        lines.append(f"| {k} | {b['mean_score']:.4f} | {c['mean_score']:.4f} | {c['mean_score']-b['mean_score']:+.4f} |")
    lines.append("")
    return lines


def _section_distribution(base: dict, ch: dict) -> list[str]:
    bd = base["distribution"]
    cd = ch["distribution"]

    lines = ["## Distribution（副作用监测）", ""]

    bs = bd["step_per_task"]
    cs = cd["step_per_task"]
    lines.append(f"- {_icon_for_dist_delta(bs.get('p95', 0), cs.get('p95', 0))} step_per_task p95: {bs.get('p95', 0)} → {cs.get('p95', 0)}")
    lines.append(f"  - mean: {bs.get('mean', 0)} → {cs.get('mean', 0)}, p50: {bs.get('p50', 0)} → {cs.get('p50', 0)}, max: {bs.get('max', 0)} → {cs.get('max', 0)}")

    bt = bd["approx_tokens_per_task"]
    ct = cd["approx_tokens_per_task"]
    lines.append(f"- {_icon_for_dist_delta(bt.get('p95', 0), ct.get('p95', 0))} approx_tokens p95: {bt.get('p95', 0)} → {ct.get('p95', 0)}")
    lines.append(f"  - mean: {bt.get('mean', 0)} → {ct.get('mean', 0)}, p99: {bt.get('p99', 0)} → {ct.get('p99', 0)}")

    bsa = bd["submit_attempts"]
    csa = cd["submit_attempts"]
    once_d = csa["once"] - bsa["once"]
    multi_d = csa["multiple"] - bsa["multiple"]
    zero_d = csa["zero"] - bsa["zero"]
    lines.append(
        f"- submit_attempts: once {_fmt_delta_int(bsa['once'], csa['once'])} | "
        f"multiple {_fmt_delta_int(bsa['multiple'], csa['multiple'])} | "
        f"zero {_fmt_delta_int(bsa['zero'], csa['zero'])}"
    )
    if zero_d > 0:
        lines.append(f"  - 🔴 未提交题数增加 +{zero_d}（红线）")
    elif zero_d < 0:
        lines.append(f"  - 🟢 未提交题数减少 {zero_d}")
    lines.append("")
    return lines


def _section_submission(base: dict, ch: dict) -> list[str]:
    bs = base["submission"]
    cs = ch["submission"]
    icon = _icon_for_count_delta(cs["submitted_count"] - bs["submitted_count"])
    return [
        "## Submission",
        "",
        f"- {icon} submitted: {_fmt_delta_int(bs['submitted_count'], cs['submitted_count'])} "
        f"(rate {bs['submission_rate']:.2%} → {cs['submission_rate']:.2%})",
        f"- perfect: {_fmt_delta_int(bs['n_perfect'], cs['n_perfect'])}",
        f"- zero: {_fmt_delta_int(bs['n_zero'], cs['n_zero'])} (lower better)",
        "",
    ]


def _section_failure_clusters(base: dict, ch: dict) -> list[str]:
    bc = base.get("failure_clusters") or {}
    cc = ch.get("failure_clusters") or {}
    keys = sorted(set(bc) | set(cc))
    if not keys:
        return ["## Failure clusters", "", "(both empty)", ""]
    lines = ["## Failure clusters", "", "| cluster | base | ch | Δ |", "| --- | ---: | ---: | ---: |"]
    for k in keys:
        a = bc.get(k, 0)
        b = cc.get(k, 0)
        # 失败数减少 = 改善
        icon = _icon_for_count_delta(a - b)  # higher_is_better=true: a-b 正数 = b 减少 = good
        lines.append(f"| {icon} {k} | {a} | {b} | {b-a:+d} |")
    new_clusters = [k for k in keys if k not in bc and cc.get(k, 0) > 0]
    if new_clusters:
        lines.append("")
        lines.append(f"- 🔴 新出现失败模式：{', '.join(new_clusters)}")
    lines.append("")
    return lines


def _section_per_task_diff(base: dict, ch: dict, *, top_n: int = 10) -> list[str]:
    """挑出 score 变化最大的 N 题（双向）。"""
    bt = {t["task_id"]: t for t in base.get("tasks", [])}
    ct = {t["task_id"]: t for t in ch.get("tasks", [])}
    common = set(bt) & set(ct)
    rows = []
    for tid in common:
        b = bt[tid]
        c = ct[tid]
        delta = c["score"] - b["score"]
        rows.append((tid, b.get("difficulty", "?"), b["score"], c["score"], delta))

    regressions = sorted([r for r in rows if r[4] < -0.01], key=lambda r: r[4])[:top_n]
    improvements = sorted([r for r in rows if r[4] > 0.01], key=lambda r: -r[4])[:top_n]

    lines = ["## Per-task highlights", ""]
    if regressions:
        lines.append(f"### 🔴 Top regressions (top {len(regressions)})")
        lines.append("")
        lines.append("| task | difficulty | base | ch | Δ |")
        lines.append("| --- | --- | ---: | ---: | ---: |")
        for tid, diff, b, c, d in regressions:
            lines.append(f"| {tid} | {diff} | {b:.4f} | {c:.4f} | {d:+.4f} |")
        lines.append("")
    if improvements:
        lines.append(f"### 🟢 Top improvements (top {len(improvements)})")
        lines.append("")
        lines.append("| task | difficulty | base | ch | Δ |")
        lines.append("| --- | --- | ---: | ---: | ---: |")
        for tid, diff, b, c, d in improvements:
            lines.append(f"| {tid} | {diff} | {b:.4f} | {c:.4f} | {d:+.4f} |")
        lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------

def render_diff(base: dict, ch: dict) -> str:
    sections: list[list[str]] = [
        _section_header(base, ch),
        _section_consistency(base, ch),
        _section_accuracy(base, ch),
        _section_distribution(base, ch),
        _section_submission(base, ch),
        _section_failure_clusters(base, ch),
        _section_per_task_diff(base, ch),
    ]
    flat: list[str] = []
    for s in sections:
        flat.extend(s)
    return "\n".join(flat)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", type=Path, required=True, help="基线 eval_report.json")
    ap.add_argument("--challenger", type=Path, required=True, help="挑战者 eval_report.json")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    base = json.loads(args.base.read_text())
    ch = json.loads(args.challenger.read_text())
    md = render_diff(base, ch)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(md)
        print(f"Written {args.out}")
    else:
        print(md)


if __name__ == "__main__":
    main()
