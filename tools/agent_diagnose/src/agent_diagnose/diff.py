"""prediction.csv vs gold.csv 列 multiset 比对 —— 与 scorer 的逻辑完全对齐。"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from src.eval.normalize import normalize_value


@dataclass
class ColumnSummary:
    name: str
    signature: tuple  # sorted Counter items
    sample_values: list[str]  # first 6 normalized values


@dataclass
class DiffResult:
    matched: list[tuple[ColumnSummary, ColumnSummary]]  # (pred, gold)
    extra_pred: list[ColumnSummary]
    missing_gold: list[ColumnSummary]
    pred_total: int
    gold_total: int


def _build_column_summary(name: str, values: list[Any]) -> ColumnSummary:
    normalized = [normalize_value(v) for v in values]
    signature = tuple(sorted(Counter(normalized).items()))
    sample = normalized[:6]
    return ColumnSummary(name=name, signature=signature, sample_values=sample)


def diff_csv(
    pred: tuple[list[str], list[list[Any]]] | None,
    gold: tuple[list[str], list[list[Any]]] | None,
) -> DiffResult:
    """贪心列匹配，与 scorer.score_task 的算法一致：每个 pred col 寻找未匹配的 gold col。"""
    pred_cols: list[ColumnSummary] = []
    gold_cols: list[ColumnSummary] = []

    if pred is not None:
        pcols, prows = pred
        for i, name in enumerate(pcols):
            vals = []
            for r in prows:
                vals.append(r[i] if i < len(r) else "")
            pred_cols.append(_build_column_summary(str(name), vals))

    if gold is not None:
        gcols, grows = gold
        for i, name in enumerate(gcols):
            vals = []
            for r in grows:
                vals.append(r[i] if i < len(r) else "")
            gold_cols.append(_build_column_summary(str(name), vals))

    matched: list[tuple[ColumnSummary, ColumnSummary]] = []
    used_gold: set[int] = set()

    for pc in pred_cols:
        match_idx: int | None = None
        for j, gc in enumerate(gold_cols):
            if j in used_gold:
                continue
            if pc.signature == gc.signature:
                match_idx = j
                break
        if match_idx is not None:
            used_gold.add(match_idx)
            matched.append((pc, gold_cols[match_idx]))

    matched_pred_names = {m[0].name for m in matched}
    extra_pred = [p for p in pred_cols if p.name not in matched_pred_names]
    missing_gold = [g for j, g in enumerate(gold_cols) if j not in used_gold]

    return DiffResult(
        matched=matched,
        extra_pred=extra_pred,
        missing_gold=missing_gold,
        pred_total=len(pred_cols),
        gold_total=len(gold_cols),
    )
