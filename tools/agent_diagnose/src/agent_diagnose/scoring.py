"""按需调用 src/eval/scorer.py 的 score_batch，写一份 reports/<run_id>_scored.json。

只负责"懒触发 + 写文件"，不重新实现评分逻辑。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_diagnose.config import DATA_INPUT_DIR, DATA_OUTPUT_DIR, REPORTS_DIR
from agent_diagnose.data import RunRef


def score_run_lazy(run: RunRef) -> dict[str, Any] | None:
    """读已有 scored.json；若不存在或落后于 trace 更新则现算并写入 reports/。"""
    if _scored_is_fresh(run):
        return _read_scored(run.scored_json)

    # Lazy-import scorer to avoid pulling pandas etc. on every request.
    from src.eval.scorer import score_batch  # noqa: PLC0415

    if not run.runs_dir.is_dir():
        return None
    if not DATA_OUTPUT_DIR.is_dir():
        return None

    payload = score_batch(
        predict_root=run.runs_dir,
        gold_root=DATA_OUTPUT_DIR,
        input_root=DATA_INPUT_DIR if DATA_INPUT_DIR.is_dir() else None,
        lam=0.5,
    )
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    run.scored_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return payload


def _scored_is_fresh(run: RunRef) -> bool:
    """scored.json 存在且不老于任何 trace.json。"""
    if not run.scored_json.is_file():
        return False
    if not run.runs_dir.is_dir():
        return False
    scored_mtime = run.scored_json.stat().st_mtime
    for task_dir in run.runs_dir.iterdir():
        if not task_dir.is_dir():
            continue
        trace = task_dir / "trace.json"
        if trace.is_file() and trace.stat().st_mtime > scored_mtime:
            return False
    return True


def _read_scored(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
