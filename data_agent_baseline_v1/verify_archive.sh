#!/usr/bin/env bash
# 把 tar.gz 当成"评测方拿到的成品"加载并自检：
#   1. 镜像可 docker load
#   2. 三个包 (data_agent_baseline_v1 / data_agent_baseline / data_agent_v0) 可导入
#   3. EnvModelAdapter 内带 max_retries=0
#   4. /build 只读，/entrypoint.py 存在
#   5. PID 1 = tini
#   6. --network=none 跑 task_11 必须写 error 占位 CSV，不能崩
# 必须在仓库根目录运行（需要读 data/demo/public/input/task_11）。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

ARCHIVE="${1:?usage: verify_archive.sh <archive.tar.gz>}"
[[ -f "$ARCHIVE" ]] || { echo "  ✗ $ARCHIVE not found"; exit 1; }

echo "[1/5] docker load < $ARCHIVE"
LOAD_OUT=$(docker load -i "$ARCHIVE")
echo "$LOAD_OUT"
IMAGE_TAG=$(echo "$LOAD_OUT" | awk -F': ' '/Loaded image/ {print $2; exit}')
[[ -n "$IMAGE_TAG" ]] || { echo "  ✗ couldn't parse image tag from docker load"; exit 1; }
echo "  image: $IMAGE_TAG"

echo "[2/5] Container static checks (imports / max_retries / readonly /build)"
docker run --rm --entrypoint sh "$IMAGE_TAG" -c '
set -e
PY=/build/data_agent_baseline_v1/.venv/bin/python

echo "  - python imports:"
$PY -c "import data_agent_baseline_v1, data_agent_baseline, data_agent_v0; print(\"    ok: 3 packages importable\")"

echo "  - max_retries=0 baked in EnvModelAdapter:"
$PY -c "
import inspect
from data_agent_baseline_v1.model_client import EnvModelAdapter
src = inspect.getsource(EnvModelAdapter)
assert \"max_retries=0\" in src, \"max_retries=0 NOT in EnvModelAdapter source\"
print(\"    ok\")
"

# /build 经 chmod -R a-w; 默认 755 dir → 555. 校验 mode 首位 (user 位) 没有 write (即 4/5/0/1)
echo "  - /build perms (defensive a-w applied):"
mode=$(stat -c "%a" /build)
case "$mode" in
  4*|5*|0*|1*) echo "    ok (mode=$mode, user-write stripped)" ;;
  *) echo "    FAIL: /build mode=$mode (expected 5xx after chmod -R a-w)"; exit 1 ;;
esac

echo "  - /entrypoint.py present + readable:"
test -f /entrypoint.py && echo "    ok"
'

echo "[3/5] Image ENTRYPOINT contains tini"
ENTRYPOINT=$(docker inspect --format '{{json .Config.Entrypoint}}' "$IMAGE_TAG")
echo "  entrypoint=$ENTRYPOINT"
if [[ "$ENTRYPOINT" == *tini* ]]; then
  echo "  ✓ tini wired as PID 1 (评测方默认不会 --entrypoint override)"
else
  echo "  ✗ tini NOT in ENTRYPOINT"; exit 1
fi

echo "[4/5] Offline smoke: --network=none on task_11 (must write error CSV)"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/input" "$TMP/output" "$TMP/logs"
if [[ ! -d "$REPO_ROOT/data/demo/public/input/task_11" ]]; then
  echo "  WARN: task_11 input missing in repo; skipping offline smoke"
else
  cp -r "$REPO_ROOT/data/demo/public/input/task_11" "$TMP/input/"
  docker run --rm --network=none --stop-timeout 600 \
      -v "$TMP/input:/input:ro" \
      -v "$TMP/output:/output:rw" \
      -v "$TMP/logs:/logs:rw" \
      -e MODEL_API_URL="http://10.0.0.1:8000/v1" \
      -e MODEL_API_KEY="dummy" \
      -e MODEL_NAME="qwen-plus" \
      "$IMAGE_TAG" || true

  if [[ -f "$TMP/output/task_11/prediction.csv" ]]; then
    echo "  ✓ task_11 prediction.csv written (header: $(head -1 "$TMP/output/task_11/prediction.csv"))"
  else
    echo "  ✗ no prediction.csv (entry crashed)"; exit 1
  fi
fi

echo "[5/5] Sensitive scan against image (app code only)"
hits=$(docker run --rm --entrypoint sh "$IMAGE_TAG" -c \
    "grep -rE 'sk-[A-Za-z0-9]{20,}|BAILIAN_API_KEY=[^ ]+' /build/data_agent_baseline_v1/src 2>/dev/null | head -5" \
    || true)
if [[ -n "$hits" ]]; then
  echo "  ✗ sensitive strings:"; echo "$hits"; exit 1
fi
echo "  ✓ clean"

echo
echo "=== verify_archive: PASS ($IMAGE_TAG) ==="
