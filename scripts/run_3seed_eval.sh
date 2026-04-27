#!/usr/bin/env bash
# 3-seed benchmark + enhanced_eval + (optional) diff —— EVAL_PLAN_30D 一键脚本。
#
# 设计目标：在阿里云服务器（Ali4KDD）上 nohup 后台跑，断点续跑友好（已存在的 run 跳过），
# 每轮日志独立文件，最终产出 reports/<version_id>_eval_report.json 与可选 diff.md。
#
# Usage:
#   ./scripts/run_3seed_eval.sh \
#       --agent-dir data_agent_baseline_v1 \
#       --run-script run_baseline_v1.sh \
#       --config configs/baseline_v1.local.yaml \
#       --run-id-base demo_qwen35_baseline_v1 \
#       --version-id baseline_v1_3seed \
#       [--seeds "no_seed,42,43"] \
#       [--diff-base reports/baseline_3seed_eval_report.json] \
#       [--limit N] \
#       [--skip-done]
#
# 默认 seeds：no_seed,42,43（与 baseline / v0 已有 3-seed 对齐）
#
# 三轮 run_id 命名约定：
#   - seed=no_seed → run_id = <run_id_base>
#   - seed=42      → run_id = <run_id_base>_s42
#   - seed=43      → run_id = <run_id_base>_s43
#
# 推荐部署用法（远端长跑）：
#   nohup ./scripts/run_3seed_eval.sh --agent-dir ... > runs/3seed_$(date +%Y%m%dT%H%M%S).log 2>&1 &

set -euo pipefail

# -------- defaults --------
SEEDS="no_seed,42,43"
SKIP_DONE=0
LIMIT=""
DIFF_BASE=""
AGENT_DIR=""
RUN_SCRIPT=""
CONFIG=""
RUN_ID_BASE=""
VERSION_ID=""

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
REPORTS_DIR="$REPO_ROOT/reports"
LOGS_DIR="$REPO_ROOT/reports/_3seed_logs"

usage() {
  sed -n '1,30p' "$0" >&2
  exit 1
}

# -------- arg parse --------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --agent-dir)    AGENT_DIR="$2"; shift 2 ;;
    --run-script)   RUN_SCRIPT="$2"; shift 2 ;;
    --config)       CONFIG="$2"; shift 2 ;;
    --run-id-base)  RUN_ID_BASE="$2"; shift 2 ;;
    --version-id)   VERSION_ID="$2"; shift 2 ;;
    --seeds)        SEEDS="$2"; shift 2 ;;
    --diff-base)    DIFF_BASE="$2"; shift 2 ;;
    --limit)        LIMIT="$2"; shift 2 ;;
    --skip-done)    SKIP_DONE=1; shift ;;
    -h|--help)      usage ;;
    *) echo "ERROR: unknown arg $1" >&2; usage ;;
  esac
done

for v in AGENT_DIR RUN_SCRIPT CONFIG RUN_ID_BASE VERSION_ID; do
  if [[ -z "${!v}" ]]; then
    echo "ERROR: --${v,,} (\$$v) is required" >&2
    usage
  fi
done

AGENT_DIR_ABS="$REPO_ROOT/$AGENT_DIR"
CONFIG_ABS="$AGENT_DIR_ABS/$CONFIG"
RUN_SCRIPT_ABS="$AGENT_DIR_ABS/$RUN_SCRIPT"
ARTIFACTS_DIR="$AGENT_DIR_ABS/artifacts/runs"

[[ -d "$AGENT_DIR_ABS" ]]    || { echo "ERROR: agent_dir not found: $AGENT_DIR_ABS" >&2; exit 1; }
[[ -f "$RUN_SCRIPT_ABS" ]]   || { echo "ERROR: run_script not found: $RUN_SCRIPT_ABS" >&2; exit 1; }
[[ -f "$CONFIG_ABS" ]]       || { echo "ERROR: config not found: $CONFIG_ABS" >&2; exit 1; }

mkdir -p "$REPORTS_DIR" "$LOGS_DIR"

# -------- yaml mutation helper --------
# Rewrite agent.seed and run.run_id in the yaml in place.
# - seed_value="no_seed" → 删除 seed 行（让 agent.seed=None）
# - seed_value=<int>     → 写 "  seed: <int>"
mutate_yaml() {
  local yaml="$1"
  local run_id="$2"
  local seed_value="$3"
  python3 - "$yaml" "$run_id" "$seed_value" <<'PY'
import sys, re
yaml_path, run_id, seed_value = sys.argv[1], sys.argv[2], sys.argv[3]
text = open(yaml_path).read()
# run.run_id
text = re.sub(r'(\n\s*run_id:\s*)[^\n]*', lambda m: m.group(1)+run_id, text, count=1)
# agent.seed (in agent: block)
if seed_value == "no_seed":
    text = re.sub(r'\n\s*seed:\s*[^\n]*', '', text, count=1)
else:
    if re.search(r'\n\s*seed:\s*[^\n]*', text):
        text = re.sub(r'(\n\s*seed:\s*)[^\n]*', lambda m: m.group(1)+seed_value, text, count=1)
    else:
        # inject into agent: block right after temperature line
        text = re.sub(r'(\n\s*temperature:[^\n]*\n)', r'\1  seed: '+seed_value+'\n', text, count=1)
open(yaml_path, "w").write(text)
PY
}

# -------- main loop --------
echo "[3seed] repo_root  = $REPO_ROOT"
echo "[3seed] agent_dir  = $AGENT_DIR_ABS"
echo "[3seed] run_script = $RUN_SCRIPT"
echo "[3seed] config     = $CONFIG"
echo "[3seed] run_id_base= $RUN_ID_BASE"
echo "[3seed] version_id = $VERSION_ID"
echo "[3seed] seeds      = $SEEDS"
echo "[3seed] diff_base  = ${DIFF_BASE:-<none>}"
echo "[3seed] limit      = ${LIMIT:-<full>}"
echo "[3seed] skip_done  = $SKIP_DONE"
echo

run_dirs=()
IFS=',' read -ra SEED_ARR <<< "$SEEDS"
for seed in "${SEED_ARR[@]}"; do
  if [[ "$seed" == "no_seed" ]]; then
    run_id="$RUN_ID_BASE"
  else
    run_id="${RUN_ID_BASE}_s${seed}"
  fi
  run_dir="$ARTIFACTS_DIR/$run_id"
  log_file="$LOGS_DIR/${VERSION_ID}_${run_id}.log"

  echo "[3seed] === round seed=$seed run_id=$run_id ==="

  if [[ "$SKIP_DONE" == "1" && -f "$run_dir/summary.json" ]]; then
    echo "[3seed]   skip (summary.json exists)"
  else
    mutate_yaml "$CONFIG_ABS" "$run_id" "$seed"
    echo "[3seed]   yaml mutated → run_id=$run_id seed=$seed"
    echo "[3seed]   log → $log_file"
    (
      cd "$AGENT_DIR_ABS"
      if [[ -n "$LIMIT" ]]; then
        ./"$RUN_SCRIPT" run-benchmark --limit "$LIMIT"
      else
        ./"$RUN_SCRIPT" run-benchmark
      fi
    ) > "$log_file" 2>&1
    echo "[3seed]   done seed=$seed"
  fi

  run_dirs+=("$run_dir")
done

# -------- enhanced_eval aggregation --------
out_report="$REPORTS_DIR/${VERSION_ID}_eval_report.json"
echo
echo "[3seed] === enhanced_eval → $out_report ==="
(
  cd "$REPO_ROOT"
  uv run python -m src.eval.enhanced_eval \
    --runs "${run_dirs[@]}" \
    --gold-root "$REPO_ROOT/data/demo/public/output" \
    --input-root "$REPO_ROOT/data/demo/public/input" \
    --version-id "$VERSION_ID" \
    --out "$out_report"
)

# -------- optional diff --------
if [[ -n "$DIFF_BASE" ]]; then
  if [[ ! -f "$DIFF_BASE" && ! -f "$REPO_ROOT/$DIFF_BASE" ]]; then
    echo "[3seed] WARN: --diff-base not found: $DIFF_BASE — skipping diff" >&2
  else
    base_abs="$DIFF_BASE"
    [[ -f "$REPO_ROOT/$DIFF_BASE" ]] && base_abs="$REPO_ROOT/$DIFF_BASE"
    base_id=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('version_id', 'base'))" "$base_abs")
    diff_md="$REPORTS_DIR/${base_id}_vs_${VERSION_ID}.md"
    echo
    echo "[3seed] === eval_diff → $diff_md ==="
    (
      cd "$REPO_ROOT"
      uv run python -m src.eval.eval_diff \
        --base "$base_abs" \
        --challenger "$out_report" \
        --out "$diff_md"
    )
  fi
fi

echo
echo "[3seed] all done."
echo "[3seed]   report: $out_report"
[[ -n "$DIFF_BASE" ]] && echo "[3seed]   diff:   $diff_md"
