#!/usr/bin/env bash
# 启动 agent-diagnose web 面板
# Usage:
#   ./run_diagnose.sh                       # localhost:8000，--reload
#   ./run_diagnose.sh 0.0.0.0 8000          # 公网监听
set -euo pipefail

HOST="${1:-127.0.0.1}"
PORT="${2:-8000}"

uv run uvicorn agent_diagnose.app:app --host "$HOST" --port "$PORT" --reload
