#!/usr/bin/env bash
# 在远端服务器（aliyun）后台启动 agent-diagnose web 面板。
#   绑 0.0.0.0:8000，nohup 后台，stdout/stderr 写到 diagnose.log，pid 写到 .diagnose.pid
#   重复执行会先杀掉旧进程再起新的。
#
# Usage:
#   ./serve_remote.sh [port]    默认 8000
set -euo pipefail

PORT="${1:-8000}"
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

# stop existing
if [[ -f .diagnose.pid ]]; then
  old=$(cat .diagnose.pid 2>/dev/null || echo "")
  if [[ -n "$old" ]] && kill -0 "$old" 2>/dev/null; then
    echo "stopping previous diagnose pid=$old"
    kill "$old" 2>/dev/null || true
    sleep 2
  fi
  rm -f .diagnose.pid
fi
# also kill any uvicorn for this app even if pid file lost
pkill -f 'agent_diagnose.app:app' 2>/dev/null || true
sleep 1

export PATH="$HOME/.local/bin:$PATH"

nohup uv run uvicorn agent_diagnose.app:app \
    --host 0.0.0.0 --port "$PORT" \
    --proxy-headers --forwarded-allow-ips '*' \
    > diagnose.log 2>&1 &
echo $! > .diagnose.pid

sleep 3
if curl -fsS -o /dev/null "http://127.0.0.1:$PORT/healthz"; then
  echo "  ✓ agent-diagnose up at :$PORT (pid=$(cat .diagnose.pid))"
  echo "  log: $HERE/diagnose.log"
else
  echo "  ✗ healthz failed; tail log:"
  tail -20 diagnose.log || true
  exit 1
fi
