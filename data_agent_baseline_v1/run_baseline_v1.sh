#!/usr/bin/env bash
# baseline-v1 入口：从 ../.env 注入 BAILIAN_API_KEY 到运行时 yaml，再调 agent-baseline-v1。
# Usage:
#   ./run_baseline_v1.sh status
#   ./run_baseline_v1.sh run-task task_11
#   ./run_baseline_v1.sh run-benchmark --limit 5
set -euo pipefail

ENV_FILE="$(cd "$(dirname "$0")/.." && pwd)/.env"
TEMPLATE="configs/baseline_v1.local.yaml"
RUNTIME="configs/baseline_v1.runtime.yaml"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE 不存在。请在仓库根目录的 .env 里写 BAILIAN_API_KEY=sk-..." >&2
  exit 1
fi

KEY=$(grep -E '^BAILIAN_API_KEY=' "$ENV_FILE" | head -1 | cut -d'=' -f2- | sed 's/^["'"'"']//; s/["'"'"']$//' | tr -d ' \t\r\n')
if [[ -z "$KEY" ]]; then
  echo "ERROR: $ENV_FILE 中未找到非空 BAILIAN_API_KEY=" >&2
  exit 1
fi

sed "s|PLACEHOLDER_REPLACED_AT_RUNTIME_FROM_DASHSCOPE_KEY_FILE|${KEY}|g" "$TEMPLATE" > "$RUNTIME"

unset all_proxy ALL_PROXY http_proxy HTTP_PROXY https_proxy HTTPS_PROXY 2>/dev/null || true

uv run agent-baseline-v1 "$@" --config "$RUNTIME"
