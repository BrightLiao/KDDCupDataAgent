"""数据访问层 —— 读现有 artifacts，零修改。

discover_runs() 扫两个数据源（baseline / v0），按 mtime 倒序。
load_* 函数都做轻 lru_cache（key 为 (run_id, task_id)）。
"""
from __future__ import annotations

import csv
import functools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_diagnose.config import (
    DATA_INPUT_DIR,
    DATA_OUTPUT_DIR,
    REPO_ROOT,
    REPORTS_DIR,
    RUN_SOURCES,
)


@dataclass(frozen=True)
class RunRef:
    run_id: str
    agent_kind: str  # baseline / baseline_v1 / agent_v0 / ...  详见 config.AGENT_KIND_ORDER
    runs_dir: Path  # 包含 task_<id>/ 的目录
    scored_json: Path  # reports/<run_id>_scored.json，可能不存在

    @property
    def label(self) -> str:
        return f"{self.agent_kind}/{self.run_id}"


def discover_runs() -> list[RunRef]:
    """扫描 RUN_SOURCES 下所有完成或半成品的 run，按 mtime 倒序。"""
    runs: list[RunRef] = []
    for kind, root in RUN_SOURCES:
        if not root.is_dir():
            continue
        for run_dir in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not run_dir.is_dir():
                continue
            run_id = run_dir.name
            runs.append(
                RunRef(
                    run_id=run_id,
                    agent_kind=kind,
                    runs_dir=run_dir,
                    scored_json=REPORTS_DIR / f"{run_id}_scored.json",
                )
            )
    return runs


def get_run(run_id: str) -> RunRef | None:
    for r in discover_runs():
        if r.run_id == run_id:
            return r
    return None


# ---------------------------------------------------------------------------
# Per-task loaders
# ---------------------------------------------------------------------------

def list_task_ids_in_run(run: RunRef) -> list[str]:
    return sorted(p.name for p in run.runs_dir.iterdir() if p.is_dir() and p.name.startswith("task_"))


def list_all_task_ids() -> list[str]:
    """50 题清单 — 以 data/demo/public/input 为权威。"""
    if not DATA_INPUT_DIR.is_dir():
        return []
    return sorted(p.name for p in DATA_INPUT_DIR.iterdir() if p.is_dir() and p.name.startswith("task_"))


@functools.lru_cache(maxsize=512)
def load_summary(run_id: str) -> dict[str, Any] | None:
    run = get_run(run_id)
    if run is None:
        return None
    path = run.runs_dir / "summary.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


@functools.lru_cache(maxsize=2048)
def load_trace(run_id: str, task_id: str) -> dict[str, Any] | None:
    run = get_run(run_id)
    if run is None:
        return None
    path = run.runs_dir / task_id / "trace.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


@functools.lru_cache(maxsize=2048)
def load_prediction_csv(run_id: str, task_id: str) -> tuple[list[str], list[list[str]]] | None:
    run = get_run(run_id)
    if run is None:
        return None
    path = run.runs_dir / task_id / "prediction.csv"
    return _read_csv_simple(path)


@functools.lru_cache(maxsize=512)
def load_gold_csv(task_id: str) -> tuple[list[str], list[list[str]]] | None:
    return _read_csv_simple(DATA_OUTPUT_DIR / task_id / "gold.csv")


@functools.lru_cache(maxsize=512)
def load_task_input(task_id: str) -> dict[str, Any]:
    """加载 task.json + knowledge.md + 上下文文件清单。"""
    base = DATA_INPUT_DIR / task_id
    out: dict[str, Any] = {"task_id": task_id, "exists": base.is_dir()}
    if not out["exists"]:
        return out
    task_json = base / "task.json"
    if task_json.is_file():
        try:
            out["task"] = json.loads(task_json.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            out["task"] = None

    knowledge_path = base / "context" / "knowledge.md"
    if knowledge_path.is_file():
        out["knowledge_md"] = knowledge_path.read_text(encoding="utf-8", errors="replace")

    # doc/*.md 也作领域知识
    doc_dir = base / "context" / "doc"
    docs: dict[str, str] = {}
    if doc_dir.is_dir():
        for p in sorted(doc_dir.iterdir()):
            if p.is_file() and p.suffix.lower() in (".md", ".sql"):
                try:
                    docs[p.name] = p.read_text(encoding="utf-8", errors="replace")
                except Exception:  # noqa: BLE001
                    pass
    if docs:
        out["doc_files"] = docs

    files: list[dict[str, Any]] = []
    ctx = base / "context"
    if ctx.is_dir():
        for p in sorted(ctx.rglob("*")):
            if p.is_file():
                rel = str(p.relative_to(ctx))
                files.append({"path": rel, "size": p.stat().st_size, "kind": p.suffix.lstrip(".")})
    out["context_files"] = files
    return out


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _read_csv_simple(path: Path) -> tuple[list[str], list[list[str]]] | None:
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            try:
                header = next(reader)
            except StopIteration:
                return [], []
            rows = [list(r) for r in reader]
        return [str(c) for c in header], rows
    except Exception:  # noqa: BLE001
        return None


def clear_caches() -> None:
    """trace / scored 文件被外部更新后调用。"""
    load_summary.cache_clear()
    load_trace.cache_clear()
    load_prediction_csv.cache_clear()
    load_gold_csv.cache_clear()
    load_task_input.cache_clear()
    discover_eval_reports.cache_clear()


# ---------------------------------------------------------------------------
# Enhanced eval reports (eval_report.json)  —— EVAL_PLAN_30D §1
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=8)
def discover_eval_reports() -> dict[str, dict[str, Any]]:
    """扫描 reports/*_eval_report.json，按 version_id 索引返回。

    返回 {version_id: {report content..., "_path": str}}。
    """
    out: dict[str, dict[str, Any]] = {}
    if not REPORTS_DIR.is_dir():
        return out
    for p in sorted(REPORTS_DIR.glob("*_eval_report.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        vid = data.get("version_id") or p.stem
        data["_path"] = str(p.relative_to(REPO_ROOT))
        out[vid] = data
    return out


def load_eval_report(version_id: str) -> dict[str, Any] | None:
    return discover_eval_reports().get(version_id)
