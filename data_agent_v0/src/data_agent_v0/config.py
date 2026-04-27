"""v0 config: extends baseline AppConfig with executor / planner / preload sections."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Reuse baseline contracts unchanged
from data_agent_baseline.config import (
    AgentConfig,
    DatasetConfig,
    RunConfig,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _path_value(raw_value: str | None, default_value: Path) -> Path:
    if not raw_value:
        return default_value
    candidate = Path(raw_value)
    if candidate.is_absolute():
        return candidate
    return (PROJECT_ROOT / candidate).resolve()


def _default_dataset_root() -> Path:
    return PROJECT_ROOT / "data" / "public" / "input"


def _default_run_output_dir() -> Path:
    return PROJECT_ROOT / "artifacts" / "runs"


@dataclass(frozen=True, slots=True)
class ExecutorConfig:
    flat_max_steps: int = 8
    step_timeout_seconds: int = 60


@dataclass(frozen=True, slots=True)
class PlannerConfig:
    enable_for: tuple[str, ...] = ("hard", "extreme")
    max_plan_steps: int = 5
    max_consecutive_failures: int = 3
    max_replan_count: int = 5


@dataclass(frozen=True, slots=True)
class PreloadConfig:
    max_csv_size_mb: int = 500
    inject_knowledge_md: bool = True


@dataclass(frozen=True, slots=True)
class V0AppConfig:
    dataset: DatasetConfig = field(default_factory=DatasetConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    run: RunConfig = field(default_factory=RunConfig)
    executor: ExecutorConfig = field(default_factory=ExecutorConfig)
    planner: PlannerConfig = field(default_factory=PlannerConfig)
    preload: PreloadConfig = field(default_factory=PreloadConfig)


def load_v0_config(config_path: Path) -> V0AppConfig:
    payload = yaml.safe_load(config_path.read_text()) or {}

    dataset_defaults = DatasetConfig(root_path=_default_dataset_root())
    run_defaults = RunConfig(output_dir=_default_run_output_dir())
    agent_defaults = AgentConfig()
    executor_defaults = ExecutorConfig()
    planner_defaults = PlannerConfig()
    preload_defaults = PreloadConfig()

    dataset_payload = payload.get("dataset", {})
    agent_payload = payload.get("agent", {})
    run_payload = payload.get("run", {})
    executor_payload = payload.get("executor", {})
    planner_payload = payload.get("planner", {})
    preload_payload = payload.get("preload", {})

    dataset_config = DatasetConfig(
        root_path=_path_value(dataset_payload.get("root_path"), dataset_defaults.root_path),
    )
    raw_seed = agent_payload.get("seed", agent_defaults.seed)
    seed_value = None if raw_seed is None or raw_seed == "" else int(raw_seed)
    agent_config = AgentConfig(
        model=str(agent_payload.get("model", agent_defaults.model)),
        api_base=str(agent_payload.get("api_base", agent_defaults.api_base)),
        api_key=str(agent_payload.get("api_key", agent_defaults.api_key)),
        max_steps=int(agent_payload.get("max_steps", agent_defaults.max_steps)),
        temperature=float(agent_payload.get("temperature", agent_defaults.temperature)),
        seed=seed_value,
    )

    raw_run_id = run_payload.get("run_id")
    run_id = run_defaults.run_id
    if raw_run_id is not None:
        normalized_run_id = str(raw_run_id).strip()
        run_id = normalized_run_id or None

    run_config = RunConfig(
        output_dir=_path_value(run_payload.get("output_dir"), run_defaults.output_dir),
        run_id=run_id,
        max_workers=int(run_payload.get("max_workers", run_defaults.max_workers)),
        task_timeout_seconds=int(
            run_payload.get("task_timeout_seconds", run_defaults.task_timeout_seconds)
        ),
    )

    executor_config = ExecutorConfig(
        flat_max_steps=int(executor_payload.get("flat_max_steps", executor_defaults.flat_max_steps)),
        step_timeout_seconds=int(
            executor_payload.get("step_timeout_seconds", executor_defaults.step_timeout_seconds)
        ),
    )

    planner_enable_raw = planner_payload.get("enable_for", list(planner_defaults.enable_for))
    planner_enable = tuple(str(v).lower() for v in planner_enable_raw)
    planner_config = PlannerConfig(
        enable_for=planner_enable,
        max_plan_steps=int(planner_payload.get("max_plan_steps", planner_defaults.max_plan_steps)),
        max_consecutive_failures=int(
            planner_payload.get("max_consecutive_failures", planner_defaults.max_consecutive_failures)
        ),
        max_replan_count=int(
            planner_payload.get("max_replan_count", planner_defaults.max_replan_count)
        ),
    )

    preload_config = PreloadConfig(
        max_csv_size_mb=int(preload_payload.get("max_csv_size_mb", preload_defaults.max_csv_size_mb)),
        inject_knowledge_md=bool(
            preload_payload.get("inject_knowledge_md", preload_defaults.inject_knowledge_md)
        ),
    )

    return V0AppConfig(
        dataset=dataset_config,
        agent=agent_config,
        run=run_config,
        executor=executor_config,
        planner=planner_config,
        preload=preload_config,
    )
