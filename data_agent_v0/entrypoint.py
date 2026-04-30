#!/usr/bin/env python3
"""KDDCup 提交镜像入口：遍历 /input/task_*，每题写 /output/task_*/prediction.csv。

设计原则：
- easy < medium < hard < extreme 优先级排序，前置容易题先把保底分拿到
- per-task budget = max(900s, remaining / remaining_tasks)
- 任何题失败必须写 error 占位 CSV，否则评测器把整体提交判失败
- 只在主进程用 SIGALRM；REPL 是独立 spawn 子进程，不受 alarm 影响
- 12h hard cap - 30min buffer 留给最后一波 error 占位
"""
from __future__ import annotations

import csv
import json
import logging
import sys
import time
from pathlib import Path

INPUT_ROOT = Path("/input")
OUTPUT_ROOT = Path("/output")
LOG_ROOT = Path("/logs")
LOG_PATH = LOG_ROOT / "runtime.log"

LOG_ROOT.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("kddcup")

GLOBAL_DEADLINE = time.time() + (12 * 3600 - 30 * 60)


def write_error_prediction(task_id: str, reason: str) -> None:
    out_dir = OUTPUT_ROOT / task_id
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "prediction.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["error"])
        w.writerow([reason[:500]])
    log.warning("task=%s wrote error placeholder: %s", task_id, reason[:120])


def task_priority(task_dir: Path) -> tuple[int, str]:
    try:
        info = json.loads((task_dir / "task.json").read_text())
        rank = {"easy": 0, "medium": 1, "hard": 2, "extreme": 3}.get(
            (info.get("difficulty") or "").lower(), 1
        )
    except Exception:
        rank = 1
    return (rank, task_dir.name)


def run_one_task(task_dir: Path, per_task_timeout: int) -> None:
    from data_agent_v0.submit_runner import run_task_to_csv

    out_csv = OUTPUT_ROOT / task_dir.name / "prediction.csv"
    run_task_to_csv(
        task_dir=task_dir,
        output_csv=out_csv,
        per_task_timeout=per_task_timeout,
    )


def main() -> int:
    if not INPUT_ROOT.is_dir():
        log.error("input root %s missing", INPUT_ROOT)
        return 2

    tasks = sorted(
        (d for d in INPUT_ROOT.iterdir() if d.is_dir() and d.name.startswith("task_")),
        key=task_priority,
    )
    log.info(
        "found %d tasks; deadline=%dm from now",
        len(tasks),
        int((GLOBAL_DEADLINE - time.time()) / 60),
    )

    for i, td in enumerate(tasks):
        remaining_tasks = len(tasks) - i
        remaining_time = max(60, GLOBAL_DEADLINE - time.time())
        per_task_budget = max(900, int(remaining_time / remaining_tasks))
        rank = task_priority(td)[0]
        log.info(
            "[%d/%d] task=%s diff_rank=%d budget=%ds remaining=%dm",
            i + 1,
            len(tasks),
            td.name,
            rank,
            per_task_budget,
            int(remaining_time / 60),
        )

        if remaining_time <= 60:
            write_error_prediction(td.name, "global timeout")
            continue

        try:
            run_one_task(td, per_task_budget)
            csv_path = OUTPUT_ROOT / td.name / "prediction.csv"
            if not csv_path.exists():
                write_error_prediction(td.name, "no prediction produced")
        except TimeoutError as exc:
            write_error_prediction(td.name, f"timeout: {exc}")
        except Exception as exc:
            log.exception("task=%s crashed", td.name)
            write_error_prediction(td.name, f"{type(exc).__name__}: {exc}")

    log.info("all tasks processed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
