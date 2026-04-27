"""L3 答案归一化 —— 与 src/eval/scorer.py 共享同一个 normalize_value。

通过 sys.path 在 v0 worker 子进程内引入 repo 根目录下的 src/eval/normalize.py。
test_normalize_parity.py 强制断言 v0 这边的 normalize_value 与 scorer 是同一个对象，
保证物理上不漂移。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Add repo root to sys.path so `src.eval.normalize` is importable from v0 worker.
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.eval.normalize import normalize_value  # noqa: E402  pylint: disable=wrong-import-position


def normalize_table(columns: list[str], rows: list[list[Any]]) -> tuple[list[str], list[list[str]]]:
    """所有 cell 走 normalize_value，列名保留原样（scorer 忽略列名）。"""
    normalized_rows = [[normalize_value(v) for v in row] for row in rows]
    return list(columns), normalized_rows


__all__ = ["normalize_value", "normalize_table"]
