"""Pure function used by the submission entrypoint.

Loads a single task, runs the v0 orchestrator, writes prediction.csv.
"""
from __future__ import annotations

import csv
import signal
from pathlib import Path

from data_agent_baseline.benchmark.dataset import DABenchPublicDataset
from data_agent_baseline.config import AgentConfig, DatasetConfig, RunConfig

from data_agent_v0.config import (
    V0AppConfig,
    ExecutorConfig,
    PlannerConfig,
    PreloadConfig,
)
from data_agent_v0.model_client import EnvModelAdapter
from data_agent_v0.orchestrator import Orchestrator


def _build_config(input_root: Path) -> V0AppConfig:
    return V0AppConfig(
        dataset=DatasetConfig(root_path=input_root),
        agent=AgentConfig(
            model="injected-by-env",
            api_base="injected-by-env",
            api_key="injected-by-env",
            max_steps=16,
            temperature=0.0,
            seed=None,
        ),
        run=RunConfig(
            output_dir=Path("/tmp/_unused"),
            run_id=None,
            max_workers=1,
            task_timeout_seconds=900,
        ),
        executor=ExecutorConfig(
            flat_max_steps=16,
            step_timeout_seconds=60,
        ),
        planner=PlannerConfig(
            enable_for=("hard", "extreme"),
            max_plan_steps=5,
            max_consecutive_failures=3,
            max_replan_count=5,
        ),
        preload=PreloadConfig(
            max_csv_size_mb=500,
            inject_knowledge_md=True,
        ),
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

    model = EnvModelAdapter(
        temperature=config.agent.temperature,
        seed=config.agent.seed,
    )
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
