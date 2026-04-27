"""位置常量：仓库根目录、各数据源相对路径。"""
from __future__ import annotations

import sys
from pathlib import Path

# tools/agent_diagnose/src/agent_diagnose/config.py → repo root
REPO_ROOT = Path(__file__).resolve().parents[4]

# Make `src.eval.scorer` importable
_REPO_PARENT_PATH = str(REPO_ROOT)
if _REPO_PARENT_PATH not in sys.path:
    sys.path.insert(0, _REPO_PARENT_PATH)

# Run sources (extend here when new agents are added)
RUN_SOURCES: list[tuple[str, Path]] = [
    ("baseline", REPO_ROOT / "kddcup2026-starter-kit" / "artifacts" / "runs"),
    ("baseline_v1", REPO_ROOT / "data_agent_baseline_v1" / "artifacts" / "runs"),
    ("v0", REPO_ROOT / "data_agent_v0" / "artifacts" / "runs"),
]

REPORTS_DIR = REPO_ROOT / "reports"
DATA_INPUT_DIR = REPO_ROOT / "data" / "demo" / "public" / "input"
DATA_OUTPUT_DIR = REPO_ROOT / "data" / "demo" / "public" / "output"

# Re-export for downstream consumers (data.py uses REPO_ROOT)
__all__ = [
    "REPO_ROOT",
    "RUN_SOURCES",
    "REPORTS_DIR",
    "DATA_INPUT_DIR",
    "DATA_OUTPUT_DIR",
]
