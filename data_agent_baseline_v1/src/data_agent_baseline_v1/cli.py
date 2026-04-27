"""baseline-v1 CLI: status / inspect-task / run-task / run-benchmark."""
from __future__ import annotations

from pathlib import Path
from time import perf_counter

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from data_agent_baseline.benchmark.dataset import DABenchPublicDataset
from data_agent_baseline.tools.filesystem import list_context_tree

from data_agent_baseline_v1.config import load_baseline_v1_config

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIGS_DIR = PROJECT_ROOT / "configs"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
ARTIFACT_RUNS_DIR = ARTIFACTS_DIR / "runs"

app = typer.Typer(add_completion=False, no_args_is_help=False)
console = Console()


def _status_value(path: Path) -> str:
    return "present" if path.exists() else "missing"


def _format_compact_rate(completed_count: int, elapsed_seconds: float) -> str:
    if completed_count <= 0 or elapsed_seconds <= 0:
        return "rate=0.0 task/min"
    return f"rate={(completed_count / elapsed_seconds) * 60:.1f} task/min"


@app.callback()
def cli() -> None:
    """baseline-v1: baseline ReAct + L1 CodeAct + L2 preload + L3 shape spec."""


@app.command()
def status(
    config: Path = typer.Option(..., exists=True, dir_okay=False, help="YAML config path."),
) -> None:
    """Show baseline-v1 project layout and dataset presence."""
    cfg = load_baseline_v1_config(config)
    config_path = config.resolve()
    public_dataset = DABenchPublicDataset(cfg.dataset.root_path)

    table = Table(title="Data Agent baseline-v1 Status")
    table.add_column("Item")
    table.add_column("Path")
    table.add_column("State")

    table.add_row("project_root", str(PROJECT_ROOT), "ready")
    table.add_row("configs_dir", str(CONFIGS_DIR), _status_value(CONFIGS_DIR))
    table.add_row("artifacts_dir", str(ARTIFACTS_DIR), _status_value(ARTIFACTS_DIR))
    table.add_row("runs_dir", str(ARTIFACT_RUNS_DIR), _status_value(ARTIFACT_RUNS_DIR))
    table.add_row("dataset_root", str(cfg.dataset.root_path), _status_value(cfg.dataset.root_path))
    table.add_row("config_path", str(config_path), _status_value(config_path))

    console.print(table)
    console.print(f"Agent model: {cfg.agent.model}")
    console.print(f"Executor flat_max_steps: {cfg.executor.flat_max_steps}")
    console.print(f"Preload inject_knowledge_md: {cfg.preload.inject_knowledge_md}")

    if public_dataset.exists:
        console.print(f"Public tasks: {len(public_dataset.list_task_ids())}")
        counts = public_dataset.task_counts()
        if counts:
            rendered = ", ".join(f"{d}={c}" for d, c in sorted(counts.items()))
            console.print(f"Public task counts: {rendered}")


@app.command("inspect-task")
def inspect_task(
    task_id: str,
    config: Path = typer.Option(..., exists=True, dir_okay=False, help="YAML config path."),
) -> None:
    """Show task metadata and available context files."""
    cfg = load_baseline_v1_config(config)
    dataset = DABenchPublicDataset(cfg.dataset.root_path)
    task = dataset.get_task(task_id)
    console.print(f"Task: {task.task_id}")
    console.print(f"Difficulty: {task.difficulty}")
    console.print(f"Question: {task.question}")
    listing = list_context_tree(task)
    table = Table(title=f"Context Files for {task.task_id}")
    table.add_column("Path")
    table.add_column("Kind")
    table.add_column("Size")
    for entry in listing["entries"]:
        table.add_row(str(entry["path"]), str(entry["kind"]), str(entry["size"] or ""))
    console.print(table)


@app.command("run-task")
def run_task_command(
    task_id: str,
    config: Path = typer.Option(..., exists=True, dir_okay=False, help="YAML config path."),
) -> None:
    """Run baseline-v1 on a single task."""
    cfg = load_baseline_v1_config(config)
    from data_agent_baseline_v1.run.runner import create_run_output_dir, run_single_task

    try:
        _, run_output_dir = create_run_output_dir(cfg.run.output_dir, run_id=cfg.run.run_id)
    except (ValueError, FileExistsError) as exc:
        raise typer.BadParameter(str(exc), param_hint="run.run_id") from exc

    artifacts = run_single_task(task_id=task_id, config=cfg, run_output_dir=run_output_dir)

    console.print(f"Run output: {run_output_dir}")
    console.print(f"Task output: {artifacts.task_output_dir}")
    if artifacts.prediction_csv_path is not None:
        console.print(f"Prediction CSV: {artifacts.prediction_csv_path}")
    else:
        console.print("Prediction CSV: not generated")
    if artifacts.failure_reason is not None:
        console.print(f"Failure: {artifacts.failure_reason}")


@app.command("run-benchmark")
def run_benchmark_command(
    config: Path = typer.Option(..., exists=True, dir_okay=False, help="YAML config path."),
    limit: int | None = typer.Option(None, min=1, help="Maximum number of tasks to run."),
) -> None:
    """Run baseline-v1 on multiple tasks."""
    cfg = load_baseline_v1_config(config)
    from data_agent_baseline_v1.run.runner import run_benchmark

    dataset = DABenchPublicDataset(cfg.dataset.root_path)
    task_total = len(dataset.iter_tasks())
    if limit is not None:
        task_total = min(task_total, limit)

    progress_columns = [
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn("[dim]|[/dim]"),
        TextColumn("[green]ok={task.fields[ok]}[/green]"),
        TextColumn("[red]fail={task.fields[fail]}[/red]"),
        TextColumn("[dim]| elapsed[/dim]"),
        TimeElapsedColumn(),
        TextColumn("[dim]| eta[/dim]"),
        TimeRemainingColumn(),
        TextColumn("{task.fields[speed]}"),
    ]
    with Progress(*progress_columns, console=console) as progress:
        progress_task_id = progress.add_task(
            "baseline-v1 Benchmark",
            total=task_total,
            completed=0,
            ok="0",
            fail="0",
            speed="rate=0.0 task/min",
        )

        completed = 0
        succeeded = 0
        failed = 0
        start = perf_counter()

        def on_task_complete(artifact) -> None:
            nonlocal completed, succeeded, failed
            completed += 1
            if artifact.succeeded:
                succeeded += 1
            else:
                failed += 1
            progress.update(
                progress_task_id,
                completed=completed,
                ok=str(succeeded),
                fail=str(failed),
                speed=_format_compact_rate(completed, perf_counter() - start),
            )

        try:
            run_output_dir, artifacts = run_benchmark(
                config=cfg,
                limit=limit,
                progress_callback=on_task_complete,
            )
        except (ValueError, FileExistsError) as exc:
            raise typer.BadParameter(str(exc), param_hint="run.run_id") from exc

    console.print(f"Run output: {run_output_dir}")
    console.print(f"Tasks attempted: {len(artifacts)}")
    console.print(f"Succeeded tasks: {sum(1 for a in artifacts if a.succeeded)}")


def main() -> None:
    app()
