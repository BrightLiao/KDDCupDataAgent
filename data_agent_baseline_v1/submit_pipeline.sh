#!/usr/bin/env bash
# 单一入口：build → archive verify → full submission verify → 给绿/红灯。
# 用法:
#   bash data_agent_baseline_v1/submit_pipeline.sh [team_id] [version]
# 或通过环境变量 TEAM_ID / VERSION 注入.
#
# 必须在仓库根目录运行（build context = repo root）。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

TEAM_ID="${1:-${TEAM_ID:-team0042}}"
VERSION="${2:-${VERSION:-baseline_v1_$(date +%Y%m%d_%H%M%S)}}"
export TEAM_ID VERSION

ARCHIVE="${TEAM_ID}_${VERSION}.tar.gz"
LOG_DIR="$REPO_ROOT/data_agent_baseline_v1/.pipeline_logs/${VERSION}"
mkdir -p "$LOG_DIR"

echo "============================================================"
echo "  submit_pipeline  team=${TEAM_ID}  version=${VERSION}"
echo "  archive (will be produced): ${ARCHIVE}"
echo "  logs: ${LOG_DIR}"
echo "============================================================"

red()  { echo "  ✗ $*"; }
green(){ echo "  ✓ $*"; }

run_stage() {
  local name="$1"; shift
  local log="$LOG_DIR/${name}.log"
  echo
  echo "──── stage: ${name} (logging to $log) ────"
  if "$@" 2>&1 | tee "$log"; then
    green "stage ${name} passed"
  else
    red "stage ${name} FAILED — see $log"
    exit 1
  fi
}

# Stage 1: build + smoke + offline + sensitive + tar.gz
run_stage build bash data_agent_baseline_v1/build_and_test_docker.sh

# Stage 2: archive self-check (load → import / tini / readonly / offline single)
run_stage archive_verify bash data_agent_baseline_v1/verify_archive.sh "$ARCHIVE"

# Stage 3: full 50-task online + enhanced_eval + diff + 11h projection
run_stage submission_verify bash data_agent_baseline_v1/verify_submission.sh "$ARCHIVE"

echo
echo "============================================================"
echo "  GREEN: $ARCHIVE ready to upload"
echo "  size: $(du -h "$ARCHIVE" | cut -f1)"
echo "============================================================"
