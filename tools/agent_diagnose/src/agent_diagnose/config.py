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

# Run sources (extend here when new agents are added).
# 命名规范：
#   baseline       原始 baseline（react + JSON action）
#   baseline_v*    在 baseline 上修问题的迭代（CodeAct + 超参等）
#   agent_v*       架构换代后的版本（v0 = 架构重写第 0 版）
RUN_SOURCES: list[tuple[str, Path]] = [
    ("baseline", REPO_ROOT / "kddcup2026-starter-kit" / "artifacts" / "runs"),
    ("baseline_v1", REPO_ROOT / "data_agent_baseline_v1" / "artifacts" / "runs"),
    ("baseline_v2", REPO_ROOT / "data_agent_baseline_v2" / "artifacts" / "runs"),
    ("agent_v0", REPO_ROOT / "data_agent_v0" / "artifacts" / "runs"),
    ("agent_v1", REPO_ROOT / "data_agent_v1" / "artifacts" / "runs"),
]

# Order used by both the overview table and the agent-summary cards.
AGENT_KIND_ORDER: list[str] = [
    "baseline",
    "baseline_v1",
    "baseline_v2",
    "agent_v0",
    "agent_v0_tuned",  # 同一份 v0 代码 + prompt 改动 (F1+F2)：shape 喂 knowledge+schema、plan/shape 合一
    "agent_v1",
]

# 同一物理目录里的不同 prompt 版本可以通过 run_id 子串映射到不同 agent_kind。
# (substring, override_kind) —— 第一个命中的 substring 生效。空 list 表示按 RUN_SOURCES 默认。
AGENT_KIND_OVERRIDES: list[tuple[str, str]] = [
    ("v5_F1F2tuned", "agent_v0_tuned"),
]

# 同一 kind 下哪些 run 算 "canonical 3-seed"，参与 5维卡 / 矩阵 / Δ 列聚合的均值。
# 不命中 substring 的 run 仍出现在 run 表中（保留 debug 价值），但从聚合排除。
# 值为子串；run_id 含此子串即 canonical。
AGENT_KIND_CANONICAL: dict[str, str] = {
    "baseline":     "_remote",  # 仅 demo_qwen35_baseline_remote* 算 canonical baseline
    "baseline_v1":  "_remote",  # 仅 demo_qwen35_baseline_v1_remote* 算 canonical (排除 docker_verify)
    "agent_v0":     "_remote",  # 仅 demo_qwen35_v0_remote* 算 canonical (排除 v0/_v2/_v3_full/_v4)
    # agent_v0_tuned: 不在表里 = 全部参与（v5_F1F2tuned 三个 seed 已是 canonical）
}

REPORTS_DIR = REPO_ROOT / "reports"
DATA_INPUT_DIR = REPO_ROOT / "data" / "demo" / "public" / "input"
DATA_OUTPUT_DIR = REPO_ROOT / "data" / "demo" / "public" / "output"

# Re-export for downstream consumers (data.py uses REPO_ROOT)
__all__ = [
    "REPO_ROOT",
    "RUN_SOURCES",
    "AGENT_KIND_ORDER",
    "AGENT_KIND_OVERRIDES",
    "AGENT_KIND_CANONICAL",
    "REPORTS_DIR",
    "DATA_INPUT_DIR",
    "DATA_OUTPUT_DIR",
]
