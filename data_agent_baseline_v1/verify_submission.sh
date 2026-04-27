#!/usr/bin/env bash
# 用 tar.gz 跑全部 50 题（在线，qwen-plus 替身评测主模型 qwen3.5-35b-a3b），
# 然后用 enhanced_eval 算 micro/macro/sub_rate，并与已有 baseline_v1 3 seed 基准比对。
# 同时把墙钟换算到 400 题（×8）来检查能否在 11h 内跑完（评测方 12h 硬上限）。
#
# 输入: $1 = archive.tar.gz
# 必须在仓库根目录运行（需要读 data/demo/public/{input,output} 与 .env）。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

ARCHIVE="${1:?usage: verify_submission.sh <archive.tar.gz>}"
[[ -f "$ARCHIVE" ]] || { echo "  ✗ $ARCHIVE not found"; exit 1; }
[[ -f "$REPO_ROOT/.env" ]] || { echo "  ✗ $REPO_ROOT/.env required (BAILIAN_API_KEY)"; exit 1; }

# load image
LOAD_OUT=$(docker load -i "$ARCHIVE")
IMAGE_TAG=$(echo "$LOAD_OUT" | awk -F': ' '/Loaded image/ {print $2; exit}')
[[ -n "$IMAGE_TAG" ]] || { echo "  ✗ couldn't parse image tag from docker load"; exit 1; }
echo "  image: $IMAGE_TAG"

# shellcheck disable=SC1091
source "$REPO_ROOT/.env"

RUN_ID="docker_verify_$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$REPO_ROOT/data_agent_baseline_v1/.verify_full"
rm -rf "$RUN_DIR"
mkdir -p "$RUN_DIR/output" "$RUN_DIR/logs"

echo "[1/3] Run all 50 demo tasks (online; qwen-plus stand-in)"
START=$(date +%s)
docker run --rm --cpus=16 --memory=64g \
    -v "$REPO_ROOT/data/demo/public/input:/input:ro" \
    -v "$RUN_DIR/output:/output:rw" \
    -v "$RUN_DIR/logs:/logs:rw" \
    -e MODEL_API_URL="https://dashscope.aliyuncs.com/compatible-mode/v1" \
    -e MODEL_API_KEY="$BAILIAN_API_KEY" \
    -e MODEL_NAME="qwen-plus" \
    "$IMAGE_TAG"
END=$(date +%s)
WALL=$((END - START))
WALL_MIN=$((WALL / 60))
PROJ_HRS=$(awk "BEGIN{printf \"%.2f\", $WALL*8/3600}")
echo "  wall=${WALL}s (~${WALL_MIN}m)"
echo "  projected on 400 hidden tasks (×8): ${PROJ_HRS}h (must be < 11h)"
if (( WALL * 8 > 11 * 3600 )); then
  echo "  ✗ projected wall > 11h, will hit evaluator 12h hard cap"; exit 1
fi
echo "  ✓ wall within budget"

# Tasks emitted by the entrypoint
N_OUT=$(find "$RUN_DIR/output" -name "prediction.csv" | wc -l | tr -d ' ')
echo "  prediction.csv count: $N_OUT / 50"
if (( N_OUT < 50 )); then
  echo "  ✗ entrypoint missed $((50-N_OUT)) tasks (must always emit, even error)"; exit 1
fi

echo "[2/3] enhanced_eval"
# Layout expected: artifacts/runs/<run_id>/task_*/prediction.csv
EVAL_RUN_DIR="$REPO_ROOT/data_agent_baseline_v1/artifacts/runs/$RUN_ID"
mkdir -p "$EVAL_RUN_DIR"
cp -r "$RUN_DIR/output/." "$EVAL_RUN_DIR/"

REPORT="$REPO_ROOT/reports/${RUN_ID}_eval_report.json"
mkdir -p "$(dirname "$REPORT")"
python3 -m src.eval.enhanced_eval \
    --runs "$EVAL_RUN_DIR" \
    --gold-root "$REPO_ROOT/data/demo/public/output" \
    --input-root "$REPO_ROOT/data/demo/public/input" \
    --version-id "${IMAGE_TAG}" \
    --out "$REPORT"

MICRO=$(python3 -c "import json; d=json.load(open('$REPORT')); print(d['accuracy']['micro_mean_score'])")
MACRO=$(python3 -c "import json; d=json.load(open('$REPORT')); print(d['accuracy']['macro_mean_score'])")
SUB=$(python3 -c "import json; d=json.load(open('$REPORT'))['submission']; print(d['submission_rate'])")
PERF=$(python3 -c "import json; d=json.load(open('$REPORT'))['submission']; print(d['n_perfect'])")
echo "  micro=$MICRO  macro=$MACRO  sub_rate=$SUB  n_perfect=$PERF"

echo "[3/3] Compare to baseline_v1 3-seed reference (tol ±0.05 micro)"
REF="$REPO_ROOT/reports/baseline_v1_3seed_remote_eval_report.json"
if [[ -f "$REF" ]]; then
  REF_MICRO=$(python3 -c "import json; print(json.load(open('$REF'))['accuracy']['micro_mean_score'])")
  python3 - "$MICRO" "$REF_MICRO" <<'PY'
import sys
m = float(sys.argv[1]); r = float(sys.argv[2])
print(f"  ref_micro={r:.4f}  this_micro={m:.4f}  delta={m-r:+.4f}")
if m + 0.05 < r:
    print(f"  ✗ regression: this_micro {m:.4f} < ref {r:.4f} - 0.05")
    sys.exit(1)
print("  ✓ within tolerance")
PY
else
  echo "  WARN: $REF missing — skip comparison"
fi

echo
echo "=== verify_submission: PASS  (micro=$MICRO, sub=$SUB, wall~${WALL_MIN}m) ==="
echo "  report: $REPORT"
