#!/usr/bin/env bash
# Re-run a list of failed tasks with max_steps=30 + 20min timeout.
# Usage:
#   ./run_retry.sh task_19 task_145 task_199 ...
set -euo pipefail

ENV_FILE="$(cd "$(dirname "$0")/.." && pwd)/.env"
TEMPLATE="configs/react_retry30.local.yaml"
RUNTIME="configs/react_retry30.runtime.yaml"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE 不存在" >&2; exit 1
fi
KEY=$(grep -E '^BAILIAN_API_KEY=' "$ENV_FILE" | head -1 | cut -d'=' -f2- | sed 's/^["'"'"']//; s/["'"'"']$//' | tr -d ' \t\r\n')
if [[ -z "$KEY" ]]; then echo "ERROR: BAILIAN_API_KEY 空" >&2; exit 1; fi

sed "s|PLACEHOLDER_REPLACED_AT_RUNTIME_FROM_DASHSCOPE_KEY_FILE|${KEY}|g" "$TEMPLATE" > "$RUNTIME"
unset all_proxy ALL_PROXY http_proxy HTTP_PROXY https_proxy HTTPS_PROXY 2>/dev/null || true

# starter-kit refuses to write into an existing run_id dir; if the retry run dir exists, run-task on individual tasks still tries to mkdir(exist_ok=False) — but since each task is a sub-dir creation, we work around by deleting and re-running the run_id.
RUN_DIR="artifacts/runs/demo_qwen35_retry30"

for tid in "$@"; do
  if [[ -d "$RUN_DIR/$tid" ]]; then
    echo "[skip] $tid already retried"
    continue
  fi
  echo "[retry] $tid"
  uv run dabench run-task "$tid" --config "$RUNTIME" || echo "  → still failed: $tid"
done
