# Docker 提交打包方案（KDDCup 2026 Data Agents）

> 依据 https://dataagent.top/rules 的 hidden test 评测要求；适用 v0 与后续版本。
> 配套 `EVAL_PLAN_30D.md`（评测策略）使用。

---

## 0. 官方约束速记

| 维度 | 规则 |
|---|---|
| 提交格式 | `<team_id>_v<N>.tar.gz`，上传 GDrive，邮件提交 |
| 镜像大小 | tar.gz ≤ 10 GB |
| 评测机 | 16 vCPU / 64 GB RAM / **无 GPU** / x86-64 |
| 全量时长 | 12h 硬性上限（≈ 100 秒/题，按 400 题计） |
| 输入路径 | `/input/task_<id>/`（read-only） |
| 输出路径 | `/output/task_<id>/prediction.csv`（read-write） |
| 日志路径 | `/logs/runtime.log`（read-write） |
| 外网 | **完全禁止**（含 OpenAI / DashScope / HuggingFace） |
| LLM | 固定 `qwen3.5-35b-a3b`，通过注入的 `MODEL_API_URL` 调用 |
| 敏感配置 | 严禁硬编码 key/url，必须读 env |
| 启动 | 必须设 `ENTRYPOINT` 或 `CMD`，`docker run <img>` 直启 |
| 提交频率 | 每天 1 次，第一阶段共 30 次，需等前次评测完成 |

### 标准启动命令（评测器视角）
```bash
docker run --rm --cpus=16 --memory=64g \
  -v /eval/data/input:/input:ro \
  -v /eval/<sub_id>/output:/output:rw \
  -v /eval/<sub_id>/logs:/logs:rw \
  -e MODEL_API_URL=<url> \
  -e MODEL_API_KEY=<key> \
  -e MODEL_NAME=qwen3.5-35b-a3b \
  team0042:v3
```

---

## 1. 改造路线总览

| 步骤 | 工作量 | 阻塞关系 |
|---|---|---|
| ① 模型适配层（env 优先，BAILIAN 兜底） | ~30 行 | 无 |
| ② 入口脚本 `entrypoint.py` + `run_task_to_csv` 包装 | ~150 行 | 依赖 ① |
| ③ Dockerfile（CPU-only 多阶段） | ~40 行 | 依赖 ② |
| ④ smoke test 脚本（含 `--network=none` 验证） | ~80 行 | 依赖 ③ |
| ⑤ 提交打包脚本 | ~20 行 | 依赖 ④ |

**节奏建议**：3 天内做完 ①-④，第 4 天做镜像内全量 50 题压测拿真实 wall time，第 5 天做正式提交准备。

---

## 2. 模型适配层（Step ①）

### 2.1 设计要点

- 评测时读 `MODEL_API_URL` / `MODEL_API_KEY` / `MODEL_NAME`
- 本地开发回退到 `BAILIAN_API_KEY` + dashscope endpoint + qwen-plus
- **绝不在 yaml / 代码里写真实 key**
- 不准 print 或 log 任何 key（防敏感泄露被判违规）

### 2.2 参考实现

替换 baseline / v0 里现有的 model client 构造：

```python
# data_agent_v0/model_client.py（新增）
import os
from openai import OpenAI

_BAILIAN_DEFAULT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

def build_client_and_model() -> tuple[OpenAI, str]:
    """env 优先；本地开发回退到 BAILIAN。"""
    base_url = os.environ.get("MODEL_API_URL") or _BAILIAN_DEFAULT_URL
    api_key  = (
        os.environ.get("MODEL_API_KEY")
        or os.environ.get("BAILIAN_API_KEY")
        or "EMPTY"
    )
    model_name = os.environ.get("MODEL_NAME") or "qwen-plus"
    return OpenAI(base_url=base_url, api_key=api_key), model_name
```

### 2.3 必须连带改动

- `configs/react_baseline.local.yaml` 和 `react_retry30.local.yaml` 的 key 字段全部删除或改 placeholder
- `run_baseline.sh` 里的 `sed` 替换 placeholder 的逻辑要保留（本地仍可用），但**镜像里不要包含 yaml 里写 key 的版本**
- grep 全代码：`grep -rE "sk-|BAILIAN" src/` 确认无硬编码

---

## 3. 入口脚本 `entrypoint.py`（Step ②）

### 3.1 不可妥协的设计原则

1. **任何题失败都要写 `prediction.csv`**（哪怕是空表 / 错误占位），否则评测器可能把整体提交判失败
2. **全局 12h 硬切**——末段必须能优雅退出，不能让评测器强制 kill
3. **easy 优先排序**——预算耗尽时 hard 题 fallback 写空表，至少把保底分拿到
4. **per-task 预算动态分配**：剩余时间 / 剩余题数，避免前面慢、后面饿死
5. **per-task SIGALRM 硬超时**：单题卡死不能拖累全局
6. **完整异常隔离**：单题崩溃只影响该题，不影响后续

### 3.2 参考实现

```python
#!/usr/bin/env python3
"""KDDCup 提交入口：遍历 /input/task_*，每题写 /output/task_*/prediction.csv"""
from __future__ import annotations
import csv, json, logging, os, signal, sys, time, traceback
from pathlib import Path

INPUT_ROOT  = Path("/input")
OUTPUT_ROOT = Path("/output")
LOG_PATH    = Path("/logs/runtime.log")

LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("kddcup")

# 12h - 30min buffer
GLOBAL_DEADLINE = time.time() + (12 * 3600 - 30 * 60)


def write_empty_prediction(task_id: str, reason: str) -> None:
    out_dir = OUTPUT_ROOT / task_id
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "prediction.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["error"])
        w.writerow([reason[:200]])
    log.warning("task=%s wrote empty prediction: %s", task_id, reason)


def run_one_task(task_dir: Path) -> None:
    """适配你的 v0 入口；必须最终写出 OUTPUT_ROOT/<task_id>/prediction.csv"""
    from data_agent_v0.cli import run_task_to_csv  # 见 §3.3
    out_dir = OUTPUT_ROOT / task_dir.name
    out_dir.mkdir(parents=True, exist_ok=True)
    run_task_to_csv(task_dir=task_dir, output_csv=out_dir / "prediction.csv")


def task_priority(d: Path) -> int:
    try:
        j = json.loads((d / "task.json").read_text())
        return {"easy": 0, "medium": 1, "hard": 2, "extreme": 3}.get(
            j.get("difficulty", ""), 1
        )
    except Exception:
        return 1


def main() -> int:
    if not INPUT_ROOT.exists():
        log.error("input root %s missing", INPUT_ROOT)
        return 2

    tasks = sorted(d for d in INPUT_ROOT.iterdir()
                   if d.is_dir() and d.name.startswith("task_"))
    log.info("found %d tasks", len(tasks))
    tasks.sort(key=task_priority)

    start_time = time.time()
    for i, td in enumerate(tasks):
        remaining_tasks = len(tasks) - i
        remaining_time  = max(60, GLOBAL_DEADLINE - time.time())
        per_task_budget = max(30, int(remaining_time / remaining_tasks))
        log.info("[%d/%d] task=%s budget=%ds remaining=%dm",
                 i + 1, len(tasks), td.name, per_task_budget,
                 int(remaining_time / 60))

        if remaining_time <= 60:
            write_empty_prediction(td.name, "global timeout")
            continue

        def _to(*_): raise TimeoutError("per-task timeout")
        old = signal.signal(signal.SIGALRM, _to)
        signal.alarm(per_task_budget)
        try:
            run_one_task(td)
        except TimeoutError:
            write_empty_prediction(td.name, f"timeout after {per_task_budget}s")
        except Exception as e:
            log.exception("task=%s crashed", td.name)
            write_empty_prediction(td.name, f"{type(e).__name__}: {e}")
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)

    log.info("done; total elapsed: %.0fs", time.time() - start_time)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### 3.3 v0 必须暴露的薄包装

在 `data_agent_v0/cli.py` 加一个纯函数，**让 entrypoint 不感知 v0 内部架构**：

```python
def run_task_to_csv(task_dir: Path, output_csv: Path) -> None:
    """提交镜像专用入口：load task → run orchestrator → 写 csv。"""
    from data_agent_baseline.benchmark.schema import PublicTask
    from data_agent_v0.config import V0AppConfig
    from data_agent_v0.model_client import build_client_and_model
    from data_agent_v0.orchestrator import Orchestrator

    task = PublicTask.load(task_dir)
    client, model_name = build_client_and_model()
    config = V0AppConfig.from_env(model_name=model_name)
    orch = Orchestrator(model=_make_adapter(client, model_name), config=config)
    result, _trace = orch.run(task)

    if result.answer is None:
        # 写错误占位
        with open(output_csv, "w", newline="") as f:
            csv.writer(f).writerows([["error"], [result.failure_reason or "no_answer"]])
        return

    with open(output_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(result.answer.columns)
        for row in result.answer.rows:
            w.writerow(row)
```

---

## 4. Dockerfile（Step ③）

放 `data_agent_v0/Dockerfile`：

```dockerfile
# syntax=docker/dockerfile:1.7

# ---- Stage 1: builder ----
FROM python:3.11-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential gcc \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv==0.4.27

WORKDIR /build

COPY pyproject.toml uv.lock ./
RUN uv venv /opt/venv && \
    uv pip install --python /opt/venv/bin/python --no-cache \
        -r <(uv pip compile pyproject.toml)

# ---- Stage 2: runtime ----
FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app/src"

RUN apt-get update && apt-get install -y --no-install-recommends \
        sqlite3 libsqlite3-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

COPY src/ ./src/
COPY entrypoint.py ./entrypoint.py

# 不可写镜像内代码
RUN chmod -R a-w /app

# 不内置任何 key；MODEL_API_URL/KEY/NAME 由评测注入
ENTRYPOINT ["python", "/app/entrypoint.py"]
```

### 4.1 配套 `.dockerignore`

```
__pycache__/
*.pyc
.venv/
.env
.env.*
*.local.yaml
*.runtime.yaml
artifacts/
data/
tests/
.git/
.pytest_cache/
.ruff_cache/
*.log
*.tar
*.tar.gz
EVAL_PLAN_30D.md
DOCKER_PACKAGING.md
```

### 4.2 镜像大小预估

- python:3.11-slim ≈ 130 MB
- 依赖（pandas / duckdb / openai / numpy / pyarrow）≈ 600 MB-1 GB
- 代码 < 5 MB
- **总计 ~1 GB**，远低于 10 GB 上限

---

## 5. 本地构建 + smoke test 脚本（Step ④）

放 `data_agent_v0/scripts/build_and_test_docker.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail

TEAM_ID="${TEAM_ID:-team0042}"
VERSION="${VERSION:-v$(date +%Y%m%d_%H%M)}"
IMAGE_TAG="${TEAM_ID}:${VERSION}"
ARCHIVE="${TEAM_ID}_${VERSION}.tar.gz"

echo "==> Building $IMAGE_TAG (linux/amd64)"
docker buildx build --platform linux/amd64 --load -t "$IMAGE_TAG" .

echo "==> Image size:"
docker images "$IMAGE_TAG" --format "  {{.Size}}"

# ---- Smoke test on 5 demo tasks ----
SMOKE_INPUT="$(pwd)/.smoke/input"
SMOKE_OUTPUT="$(pwd)/.smoke/output"
SMOKE_LOGS="$(pwd)/.smoke/logs"
rm -rf "$SMOKE_INPUT" "$SMOKE_OUTPUT" "$SMOKE_LOGS"
mkdir -p "$SMOKE_INPUT" "$SMOKE_OUTPUT" "$SMOKE_LOGS"

for t in task_11 task_56 task_163 task_180 task_344; do
  cp -r "../data/demo/public/input/$t" "$SMOKE_INPUT/"
done

echo "==> Smoke test (online, BAILIAN as proxy for inner endpoint)"
source ../.env
docker run --rm \
  --cpus=16 --memory=64g \
  -v "$SMOKE_INPUT:/input:ro" \
  -v "$SMOKE_OUTPUT:/output:rw" \
  -v "$SMOKE_LOGS:/logs:rw" \
  -e MODEL_API_URL="https://dashscope.aliyuncs.com/compatible-mode/v1" \
  -e MODEL_API_KEY="$BAILIAN_API_KEY" \
  -e MODEL_NAME="qwen-plus" \
  "$IMAGE_TAG"

echo "==> Verify outputs:"
for t in task_11 task_56 task_163 task_180 task_344; do
  csv="$SMOKE_OUTPUT/$t/prediction.csv"
  [[ -f "$csv" ]] || { echo "MISSING: $csv"; exit 1; }
  echo "  $csv ($(wc -l <"$csv") lines)"
done

echo "==> Verify offline behavior (--network=none should NOT crash entry)"
docker run --rm --network=none \
  -v "$SMOKE_INPUT:/input:ro" \
  -v "$SMOKE_OUTPUT:/output:rw" \
  -v "$SMOKE_LOGS:/logs:rw" \
  -e MODEL_API_URL="http://10.0.0.1:8000/v1" \
  -e MODEL_API_KEY="dummy" \
  -e MODEL_NAME="qwen3.5-35b-a3b" \
  "$IMAGE_TAG" || true
# 离线下应当对每题写 error prediction.csv，而不是 entry 自己崩
echo "==> Offline mode produced these predictions:"
find "$SMOKE_OUTPUT" -name "prediction.csv" -newer "$SMOKE_INPUT" | head -5

echo "==> Sensitive scan (should be empty)"
docker save "$IMAGE_TAG" | tar -tv 2>/dev/null | head -50  # sanity
docker run --rm --entrypoint sh "$IMAGE_TAG" -c \
  "grep -rEi 'sk-|BAILIAN_API_KEY' /app /opt/venv 2>/dev/null | head -5" \
  && { echo "FAIL: sensitive strings found in image"; exit 1; } \
  || echo "  no sensitive strings"

echo "==> Packaging $ARCHIVE"
docker save "$IMAGE_TAG" | gzip > "$ARCHIVE"
ls -lh "$ARCHIVE"

# 检查 archive ≤ 10 GB
size=$(stat -f%z "$ARCHIVE" 2>/dev/null || stat -c%s "$ARCHIVE")
if (( size > 10 * 1024 * 1024 * 1024 )); then
  echo "FAIL: archive > 10 GB"; exit 1
fi
echo "==> Ready to upload: $ARCHIVE"
```

### 5.1 必须做的 smoke check

| 检查 | 失败的后果 |
|---|---|
| `--platform linux/amd64`（Mac arm64 默认会构 arm 镜像） | 评测机起不来 |
| `--network=none` 不让 entry 崩，至少能写 error prediction.csv | 评测时所有题失败 |
| `--cpus=16 --memory=64g` 模拟资源 | 本地不限资源跑得快，评测慢 8x，超时 |
| 5 题都产出 prediction.csv | 评测器把整体提交判失败 |
| `grep` 镜像里没有 `sk-` / `BAILIAN_API_KEY` | 违规取消资格 |
| archive ≤ 10 GB | 评测器拒收 |

---

## 6. 镜像内全量 50 题压测（Step ⑤）

build_and_test_docker.sh 验证完 5 题后，**必须再做完整 50 题镜像内压测**：

```bash
SMOKE_INPUT="$(pwd)/.full/input"   # 拷整个 demo input
cp -r ../data/demo/public/input/* "$SMOKE_INPUT/"
# 跑全量，记录 wall time
time docker run --rm --cpus=16 --memory=64g \
  -v "$SMOKE_INPUT:/input:ro" \
  -v "$SMOKE_OUTPUT:/output:rw" \
  -v "$SMOKE_LOGS:/logs:rw" \
  -e MODEL_API_URL="$BAILIAN_URL" \
  -e MODEL_API_KEY="$BAILIAN_API_KEY" \
  -e MODEL_NAME="qwen-plus" \
  "$IMAGE_TAG"
```

**外推到 400 题**：
- 50 题真实 wall time / 50 × 400 = 完整评测预估
- 超过 11h（留 1h buffer）必须砍 `max_steps` / 缩 `step_timeout`

---

## 7. 提交流程

### 7.1 提交前最终 checklist

```
[ ] git tag <team_id>_v<N>
[ ] build_and_test_docker.sh 全绿（5 题 smoke + offline + sensitive scan）
[ ] 镜像内全量 50 题 wall time × 8 < 12h
[ ] archive ≤ 10 GB
[ ] git status 干净（提交内容与 tag 一致）
[ ] EVAL_PLAN_30D 的 5 条提交硬门槛全过
[ ] hypothesis YAML 已写
[ ] 距收尾期还有足够 buffer
```

### 7.2 提交动作

1. 上传 `<team_id>_v<N>.tar.gz` 到 Google Drive
2. 共享链接（任何人可下载）
3. 邮件给评委会（按官方公告地址）
4. 在 `submission_log.md` 记录：Day / version / hypothesis / 预测 hidden 分 / 提交时间
5. 收到评测结果后回填 actual / classification

### 7.3 提交后

- **不要立刻提交下一版**——必须等结果回来，对比预测，更新折算系数 K
- 把 trace + log 归档到 `artifacts/submissions/<version>/`，便于事后复盘

---

## 8. 常见 docker-only bug 自检

镜像里跑和本地裸跑会暴露的 bug：

| Bug 类 | 表现 | 检查 |
|---|---|---|
| `sys.path.insert` hack | 镜像里 import 失败 | Dockerfile 设 `PYTHONPATH=/app/src`，本地 dev 模式与镜像保持一致 |
| 相对路径硬编码 | `Path("../data/...")` 在 docker 里找不到 | grep `../` 全部改成绝对路径或 env 注入 |
| CRLF 行为差异 | Mac 下宽容，Linux 下报错 | smoke test 在 docker 里复现 |
| multiprocessing spawn + PID 1 | REPL worker 起不来 | `--init` flag（评测器可能不会带，最好在 entrypoint 用 `tini` 包一层） |
| SIGALRM 在多线程中失效 | per-task 超时不生效 | 主进程单线程跑入口，alarm 在主线程 |
| openai 客户端 retry 在断网下死循环 | offline 模式 entry 卡死 | 显式设 `max_retries=0`，自己实现 retry |

---

## 9. 仍需向组织者确认的问题

发邮件 / Discord 问 Boyan Li / Yuyu Luo（dataagent.top 上的联系方式）：

1. `qwen3.5-35b-a3b` 的 OpenAI 兼容 endpoint 是否支持 `tools` / `function_calling`？
2. 内部 endpoint 的并发上限和 RPS？影响是否能并行跑多题
3. 单次评测的实际排队 + 跑完时长？影响 30 次配额的真实节奏
4. 是否支持 JSON mode / structured output？影响 plan parser 设计
5. 是否提供官方测试 endpoint 给参赛者本地跑？避免 dashscope qwen-plus 与评测时 qwen3.5-35b-a3b 行为差太大
6. 提交镜像后的"评测完成"通知方式？邮件 / dashboard / API？
7. tar.gz 加载方式：是 `docker load` 还是 `docker import`？影响是否需要保留多 layer 信息

---

## 10. 文件落位

```
data_agent_v0/
├── Dockerfile                      # §4
├── .dockerignore                   # §4.1
├── entrypoint.py                   # §3
├── pyproject.toml
├── uv.lock
├── src/
│   └── data_agent_v0/
│       ├── cli.py                  # 加 run_task_to_csv (§3.3)
│       ├── model_client.py         # §2.2 新增
│       ├── orchestrator.py
│       └── ...
├── scripts/
│   └── build_and_test_docker.sh    # §5
├── DOCKER_PACKAGING.md             # 本文档
└── EVAL_PLAN_30D.md                # 配套评测策略
```

---

## 11. 一句话

**核心差异在适配层 + entrypoint + Dockerfile 三个工程动作，不在算法**。先做好 §1-§5 的工程闭环（含 `--network=none` 验证 + 镜像内全量 50 题压测），算法迭代才有意义；任何算法改动都必须先过镜像 smoke test 才能进入 EVAL_PLAN_30D 的提交流程。
