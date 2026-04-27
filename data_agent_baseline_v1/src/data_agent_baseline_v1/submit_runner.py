"""Pure function used by the submission entrypoint.

Loads a single task, runs the baseline_v1 orchestrator, writes prediction.csv.
单线程主进程内调用：用 SIGALRM 包一层 wallclock 超时，REPL spawn worker 出错或卡死时
orchestrator.run() 的 try/finally 会负责 repl.shutdown()。
"""
from __future__ import annotations

import csv
import signal
from pathlib import Path

from data_agent_baseline.benchmark.dataset import DABenchPublicDataset
from data_agent_baseline.config import AgentConfig, DatasetConfig, RunConfig

from data_agent_baseline_v1.config import (
    BaselineV1AppConfig,
    ExecutorConfig,
    PreloadConfig,
)
from data_agent_baseline_v1.model_client import EnvModelAdapter
from data_agent_baseline_v1.orchestrator import Orchestrator


def _build_config(input_root: Path) -> BaselineV1AppConfig:
    return BaselineV1AppConfig(
        dataset=DatasetConfig(root_path=input_root),
        agent=AgentConfig(
            model="injected-by-env",  # actual name read by EnvModelAdapter
            api_base="injected-by-env",
            api_key="injected-by-env",
            max_steps=24,
            temperature=0.0,
            seed=None,
        ),
        run=RunConfig(output_dir=Path("/tmp/_unused"), run_id=None, max_workers=1),
        executor=ExecutorConfig(
            flat_max_steps=24,
            step_timeout_seconds=60,
            max_consecutive_failures=3,
        ),
        preload=PreloadConfig(max_csv_size_mb=100, inject_knowledge_md=True),
    )


def _write_error_csv(output_csv: Path, reason: str) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["error"])
        w.writerow([reason[:500]])


def run_task_to_csv(
    *,
    task_dir: Path,
    output_csv: Path,
    per_task_timeout: int,
) -> None:
    """task_dir = /input/task_<id>; output_csv = /output/task_<id>/prediction.csv."""
    input_root = task_dir.parent
    task_id = task_dir.name

    config = _build_config(input_root)
    dataset = DABenchPublicDataset(config.dataset.root_path)
    task = dataset.get_task(task_id)

    model = EnvModelAdapter(temperature=config.agent.temperature, seed=config.agent.seed)
    orchestrator = Orchestrator(model=model, config=config)

    def _on_timeout(*_):
        raise TimeoutError(f"per-task timeout {per_task_timeout}s")

    old_handler = signal.signal(signal.SIGALRM, _on_timeout)
    signal.alarm(max(900, per_task_timeout))
    try:
        result, _ot = orchestrator.run(task)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    if result.answer is None:
        _write_error_csv(output_csv, result.failure_reason or "no_answer")
        return

    with output_csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(result.answer.columns)
        for row in result.answer.rows:
            w.writerow(row)
