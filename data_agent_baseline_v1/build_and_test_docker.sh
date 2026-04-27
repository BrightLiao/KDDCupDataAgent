#!/usr/bin/env bash
# baseline-v1 镜像构建 + smoke + 离线测试 + sensitive scan + 打包。
# 必须在仓库根目录运行（build context = repo root）。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

TEAM_ID="${TEAM_ID:-team0042}"
VERSION="${VERSION:-baseline_v1_$(date +%Y%m%d)}"
IMAGE_TAG="${TEAM_ID}:${VERSION}"
ARCHIVE="${TEAM_ID}_${VERSION}.tar.gz"

DOCKERFILE="data_agent_baseline_v1/Dockerfile"
SMOKE_DIR="$REPO_ROOT/data_agent_baseline_v1/.smoke"
SMOKE_TASKS=(task_11 task_56 task_163 task_180 task_344)

echo "[1/7] Building $IMAGE_TAG (linux/amd64)"
if docker buildx version >/dev/null 2>&1; then
  docker buildx build --platform linux/amd64 --load \
      -f "$DOCKERFILE" -t "$IMAGE_TAG" .
else
  # Native classic builder; aliyun host is amd64 already.
  DOCKER_BUILDKIT=1 docker build -f "$DOCKERFILE" -t "$IMAGE_TAG" .
fi

echo "[2/7] Image size:"
docker images "$IMAGE_TAG" --format "  {{.Size}}"

echo "[3/7] Prepare smoke task fixtures"
rm -rf "$SMOKE_DIR"
mkdir -p "$SMOKE_DIR"/{input,output,logs}
for t in "${SMOKE_TASKS[@]}"; do
  if [[ ! -d "$REPO_ROOT/data/demo/public/input/$t" ]]; then
    echo "  WARN: $t not found in data/demo/public/input — skipping"
    continue
  fi
  cp -r "$REPO_ROOT/data/demo/public/input/$t" "$SMOKE_DIR/input/"
done

echo "[4/7] Smoke test (online via BAILIAN; MODEL_NAME=qwen-plus stand-in)"
if [[ ! -f "$REPO_ROOT/.env" ]]; then
  echo "  ERROR: $REPO_ROOT/.env required for smoke test (BAILIAN_API_KEY)"
  exit 1
fi
# shellcheck disable=SC1091
source "$REPO_ROOT/.env"
docker run --rm --cpus=16 --memory=64g \
    -v "$SMOKE_DIR/input:/input:ro" \
    -v "$SMOKE_DIR/output:/output:rw" \
    -v "$SMOKE_DIR/logs:/logs:rw" \
    -e MODEL_API_URL="https://dashscope.aliyuncs.com/compatible-mode/v1" \
    -e MODEL_API_KEY="$BAILIAN_API_KEY" \
    -e MODEL_NAME="qwen-plus" \
    "$IMAGE_TAG"

echo "[4.1/7] Verify smoke outputs"
for t in "${SMOKE_TASKS[@]}"; do
  csv="$SMOKE_DIR/output/$t/prediction.csv"
  if [[ -f "$csv" ]]; then
    echo "  ✓ $t : $(wc -l <"$csv") lines"
  else
    echo "  ✗ $t : MISSING"; exit 1
  fi
done

echo "[5/7] Offline test (--network=none must produce error CSVs, not crash)"
rm -rf "$SMOKE_DIR/output_offline" && mkdir -p "$SMOKE_DIR/output_offline"
docker run --rm --network=none --stop-timeout 600 \
    -v "$SMOKE_DIR/input:/input:ro" \
    -v "$SMOKE_DIR/output_offline:/output:rw" \
    -v "$SMOKE_DIR/logs:/logs:rw" \
    -e MODEL_API_URL="http://10.0.0.1:8000/v1" \
    -e MODEL_API_KEY="dummy" \
    -e MODEL_NAME="qwen3.5-35b-a3b" \
    "$IMAGE_TAG" || true

echo "[5.1/7] Offline must have error placeholder CSVs:"
for t in "${SMOKE_TASKS[@]}"; do
  csv="$SMOKE_DIR/output_offline/$t/prediction.csv"
  if [[ -f "$csv" ]]; then
    echo "  ✓ $t : $(head -1 "$csv")"
  else
    echo "  ✗ $t : entry crashed without writing CSV"; exit 1
  fi
done

echo "[6/7] Sensitive scan (only /build app code, NOT /opt/venv deps)"
hits=$(docker run --rm --entrypoint sh "$IMAGE_TAG" -c \
    "grep -rE 'sk-[A-Za-z0-9]{20,}|BAILIAN_API_KEY=[^ ]+' /build/data_agent_baseline_v1/src 2>/dev/null | head -5" \
    || true)
if [[ -n "$hits" ]]; then
  echo "  ✗ FAIL: sensitive strings found:"
  echo "$hits"
  exit 1
fi
echo "  ✓ no sensitive strings"

echo "[7/7] Save & gzip → $ARCHIVE"
docker save "$IMAGE_TAG" | gzip > "$ARCHIVE"
size=$(stat -c%s "$ARCHIVE" 2>/dev/null || stat -f%z "$ARCHIVE")
size_gb=$(awk "BEGIN{printf \"%.2f\", $size/1024/1024/1024}")
echo "  archive: $ARCHIVE (${size_gb} GB)"
if (( size > 10 * 1024 * 1024 * 1024 )); then
  echo "  ✗ FAIL: archive > 10 GB"; exit 1
fi
echo "  ✓ archive ≤ 10 GB"

echo
echo "=== ready to upload: $ARCHIVE ==="
