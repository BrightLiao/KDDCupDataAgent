#!/usr/bin/env bash
# Wrapper that injects BAILIAN_API_KEY from ../.env into the local config at run time.
# Usage:
#   ./run_baseline.sh status
#   ./run_baseline.sh run-task task_11
#   ./run_baseline.sh run-benchmark --limit 5
set -euo pipefail

ENV_FILE="$(cd "$(dirname "$0")/.." && pwd)/.env"
TEMPLATE="configs/react_baseline.local.yaml"
RUNTIME="configs/react_baseline.runtime.yaml"  # gitignored, built each run

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE 不存在。请在项目根目录的 .env 里写 BAILIAN_API_KEY=sk-..." >&2
  exit 1
fi
# Read BAILIAN_API_KEY from .env (strip optional quotes/whitespace)
KEY=$(grep -E '^BAILIAN_API_KEY=' "$ENV_FILE" | head -1 | cut -d'=' -f2- | sed 's/^["'"'"']//; s/["'"'"']$//' | tr -d ' \t\r\n')
if [[ -z "$KEY" ]]; then
  echo "ERROR: $ENV_FILE 中未找到非空 BAILIAN_API_KEY=" >&2
  exit 1
fi

# Build runtime config: substitute the placeholder with real key
sed "s|PLACEHOLDER_REPLACED_AT_RUNTIME_FROM_DASHSCOPE_KEY_FILE|${KEY}|g" "$TEMPLATE" > "$RUNTIME"

# Bailian (dashscope.aliyuncs.com) is on the public internet; if we go through
# a local SOCKS proxy without socksio installed, httpx fails. Easiest: bypass
# the proxy for Aliyun domains. We unset all proxy vars by default — Aliyun
# from China typically doesn't need a proxy and the requests are HTTPS direct.
unset all_proxy ALL_PROXY http_proxy HTTP_PROXY https_proxy HTTPS_PROXY 2>/dev/null || true

uv run dabench "$@" --config "$RUNTIME"
