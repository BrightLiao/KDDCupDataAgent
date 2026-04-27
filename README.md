# KDD Cup 2026 — Data Agents 参赛仓库

针对 [KDD Cup 2026 Track: Data Agents for Complex Data Analysis](https://dataagent.top/) 的方案、基线复跑、评测、诊断与提交打包。

> 比赛任务：给定一个数据科学问题（自然语言）+ 一组多模态数据资产（CSV / SQLite / JSON / 文档），agent 自主探索、推理、产出表格答案 `prediction.csv`。
> 评分：`Score = Recall − λ · (Extra Columns / Predicted Columns)`，列以 multiset 比对（忽略列名 / 行序），λ=0.5。
> 后端 LLM：Qwen3.5-35B-A3B（阿里云百炼，OpenAI 兼容 API）。

---

## 当前进度（2026-04-27，3 seed × 50 题 demo public）

| Agent | 路径 | Micro | Macro | Sub Rate | n_perfect / 50 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| baseline (官方 ReAct) | [kddcup2026-starter-kit/](kddcup2026-starter-kit/) | 0.376 | 0.327 | 80% | 7 | 受 JSON action 解析失败拖累 |
| **baseline_v1**（推荐提交） | [data_agent_baseline_v1/](data_agent_baseline_v1/) | **0.585** | **0.436** | **94%** | **22** | baseline + L1+L2+L3，无 planner |
| data_agent_v0 | [data_agent_v0/](data_agent_v0/) | 0.585 | 0.433 | 94% | 22 | baseline_v1 + L4 (planner + 难度路由) |

技术改进按层叠加：

- **L1 CodeAct**：替 ReAct JSON action 为 ` ```python ` 代码块，消除三引号转义死循环（arXiv:2402.01030）
- **L2 上下文预载**：启动时一次性 `head + dtypes` + `knowledge.md` 注入 prompt，省 4-6 步预算
- **L3 Shape Spec 抽取**：一次 LLM 调用从 question 解析 `expected_columns` / `expected_row_count`，submit 前列对齐
- **L4 Plan-Executor + 难度路由**（仅 v0）：planner 出短计划，executor 按 easy/medium/hard/extreme 路由不同分支

50 题 demo 上 L4 边际增益 ~0，所以**首版提交用 baseline_v1**。L4 只对 hard/extreme 一致性微正，但易题反退步并新增 api_error 失败模式。

详见 [reports/baseline_3seed_remote_vs_baseline_v1_3seed_remote.md](reports/baseline_3seed_remote_vs_baseline_v1_3seed_remote.md) 与 [reports/baseline_v1_3seed_remote_vs_v0_3seed_remote.md](reports/baseline_v1_3seed_remote_vs_v0_3seed_remote.md)。

---

## 目录结构

```text
.
├── docs/                                    # 中文方案文档
│   ├── 比赛简介.md                            # 题型 / 评分 / 难度
│   ├── 方案调研综述.md                         # CodeAct / GEPA / DS-STAR / RSL-SQL ...
│   ├── 分难度方案设计.md                       # 4 档难度的分支方案
│   ├── 改进路线图.md                          # L1-L4 路线 + 主流 agent 架构对比
│   ├── DOCKER_PACKAGING.md                  # docker 打包注意事项（5 红线）
│   └── EVAL_PLAN_30D.md                     # 30 天评测方法（5 类指标 + 3 seed）
│
├── kddcup2026-starter-kit/                  # 官方 starter-kit + 本地修订（含 retry / max_retries=0 patch）
│   └── src/data_agent_baseline/             #   ReAct agent + 8 个 tool（baseline）
│
├── data_agent_baseline_v1/                  # baseline + L1+L2+L3，无 planner（推荐提交版本）
│   ├── src/data_agent_baseline_v1/
│   ├── configs/baseline_v1.example.yaml
│   ├── Dockerfile + entrypoint.py + .dockerignore
│   ├── build_and_test_docker.sh             # 本地 build + smoke + offline + sensitive + tar.gz
│   ├── verify_archive.sh                    # 验证 tar.gz：load + 容器自检
│   ├── verify_submission.sh                 # 全 50 题在线 + enhanced_eval + 与 ref 对比
│   ├── submit_pipeline.sh                   # 单一入口：build → archive verify → submission verify
│   └── run_baseline_v1.sh                   # 直跑（非 docker）入口
│
├── data_agent_v0/                           # baseline_v1 + L4（planner + 难度路由）
│   ├── src/data_agent_v0/
│   ├── configs/v0.example.yaml
│   └── run_v0.sh
│
├── tools/agent_diagnose/                    # FastAPI + Jinja2 + HTMX 诊断面板
│   ├── src/agent_diagnose/                  # data / normalize（含 prompt 重建）/ stats / scoring / 路由
│   │   ├── templates/                       # overview / task_replay / eval + partials
│   │   └── static/                          # style.css / htmx / Prism (vendored)
│   ├── tests/
│   ├── run_diagnose.sh                      # 本地 dev :8000 --reload
│   └── serve_remote.sh                      # 远端 nohup 部署 0.0.0.0:8000
│
├── src/eval/
│   ├── scorer.py                            # 列 multiset 评分器（§6.5/§7.1）
│   └── enhanced_eval.py                     # 5 类指标聚合 (accuracy / dist / sub / failure / consist)
│
├── scripts/
│   ├── run_3seed_eval.sh                    # 3 seed × N 题 → enhanced_eval → 可选 diff vs ref
│   ├── profile_demo.py
│   └── convert_bird.py
│
├── reports/                                 # 评测产物（per-task scored.json + diff.md + html）
│   ├── baseline_3seed_remote_eval_report.json
│   ├── baseline_v1_3seed_remote_eval_report.json
│   ├── v0_3seed_remote_eval_report.json
│   └── *_vs_*.md                            # 跨版本 diff
│
├── data/                                    # demo 数据集（gitignore，~2.2G）
└── config/                                  # 云资源 key（*.pem 已 gitignore）
```

---

## 快速开始

### 1. 环境与 API key

```bash
# 三个包各自管理 venv（uv），避免 dep 冲突
cd kddcup2026-starter-kit && uv sync && cd ..
cd data_agent_baseline_v1 && uv sync && cd ..
cd data_agent_v0 && uv sync && cd ..

# 仓库根目录新建 .env (gitignore)
echo "BAILIAN_API_KEY=sk-xxxx" > .env
```

### 2. 准备 demo 数据

```text
data/demo/public/
├── input/task_<id>/      # question + 多模态 context
└── output/task_<id>/gold.csv
```

### 3. 跑 agent

```bash
# baseline (官方 ReAct)
cd kddcup2026-starter-kit && ./run_baseline.sh run-benchmark

# baseline_v1 (推荐)
cd data_agent_baseline_v1 && ./run_baseline_v1.sh

# v0 (含 L4 planner)
cd data_agent_v0 && ./run_v0.sh
```

产物：`<package>/artifacts/runs/<run_id>/task_<id>/{trace.json, prediction.csv}`

---

## 评测方法

完整方法见 [docs/EVAL_PLAN_30D.md](docs/EVAL_PLAN_30D.md)。核心：**3 seed × 50 题 → 5 类指标聚合**。

### 单 run 评分

```bash
uv run python -m src.eval.enhanced_eval \
    --runs <package>/artifacts/runs/<run_id> \
    --gold-root data/demo/public/output \
    --input-root data/demo/public/input \
    --version-id <label> \
    --out reports/<label>_eval_report.json
```

输出 5 类指标：

- **accuracy** — micro/macro mean Score（跨 run 平均）
- **distribution** — 按难度 (easy/medium/hard/extreme) × 数据类型 (csv/json/db/mixed) 拆分
- **submission** — submitted_count / submission_rate / n_perfect / n_zero
- **failure_clusters** — timeout / parse_error / api_error / no_submit / other 计数
- **consistency** — 多 run 时计算 all_agree / majority_agree / answer_entropy

### 一键 3 seed wrapper

```bash
bash scripts/run_3seed_eval.sh \
    --agent-dir data_agent_baseline_v1 \
    --run-script ./run_baseline_v1.sh \
    --config configs/baseline_v1.local.yaml \
    --run-id-base demo_qwen35_baseline_v1 \
    --version-id baseline_v1_3seed \
    --seeds no_seed,42,43 \
    --diff-base baseline_3seed
```

会跑 3 轮（无 seed / 42 / 43），各自落 run dir，最后 enhanced_eval 聚合 + 与基线 diff。脚本支持 `--skip-done` 断点续跑、`--limit N` 子集快速 smoke。

---

## Docker 打包方法

提交镜像由 [data_agent_baseline_v1/Dockerfile](data_agent_baseline_v1/Dockerfile) 构建，build context = 仓库根目录（因为 baseline_v1 通过 path-deps 依赖 ../data_agent_v0 与 ../kddcup2026-starter-kit，三个包都要 COPY 进同样相对位置）。

### 单一入口

```bash
bash data_agent_baseline_v1/submit_pipeline.sh team0042 baseline_v1_$(date +%Y%m%d)
```

串起三个 stage（任一失败立即红灯）：

| Stage | 脚本 | 作用 |
| --- | --- | --- |
| 1 build | `build_and_test_docker.sh` | buildx amd64 → 5 题 smoke (在线 BAILIAN) → `--network=none` 离线必须写 error CSV → 敏感字符串扫描 (`/build/.../src` 范围) → tar.gz + ≤10GB |
| 2 archive verify | `verify_archive.sh` | docker load → 三包导入 / `max_retries=0` baked in / `/build` 只读 / PID 1=tini / 单题 `--network=none` 必写 error CSV |
| 3 submission verify | `verify_submission.sh` | 全 50 题在线 → `enhanced_eval` → 与 baseline_v1 3-seed 基线对比 (容差 ±0.05 micro) → 墙钟 ×8 < 11h 投影 |

任一 stage 失败：日志落 `data_agent_baseline_v1/.pipeline_logs/<version>/<stage>.log`，红灯退出。

### 关键设计点

- **path-deps 多包**：`uv sync --frozen --no-dev` 在 baseline_v1 dir 内运行，自动解析 `../data_agent_v0` / `../kddcup2026-starter-kit`，三个包必须同 layout 进镜像
- **PID 1 = tini**：避免 multiprocessing.spawn 子进程（CodeAct REPL）退出后僵尸不回收
- **`max_retries=0`**：baked in `EnvModelAdapter`，`--network=none` 时 OpenAI 不死循环重试
- **SIGALRM wallclock 超时**：仅在 [submit_runner.py](data_agent_baseline_v1/src/data_agent_baseline_v1/submit_runner.py) 主进程内一处包，REPL spawn worker 不受影响
- **入口动态预算**：[entrypoint.py](data_agent_baseline_v1/entrypoint.py) 按 `max(900, remaining_time / remaining_tasks)` 分配，easy 优先排序，12h - 30min 留 buffer
- **网络受限镜像**：[Dockerfile](data_agent_baseline_v1/Dockerfile) 装 `mirrors.aliyun.com` PyPI mirror + BuildKit cache mount，国内服务器（Ali4KDD）build context = 988 KB / wheels 跨 build 复用

更详细的 5 红线说明：[docs/DOCKER_PACKAGING.md](docs/DOCKER_PACKAGING.md)。

---

## 诊断 Web 界面

[tools/agent_diagnose/](tools/agent_diagnose/) — FastAPI + Jinja2 + HTMX 内部诊断面板，无认证，部署到云服务器上小队伍直接看。

### 启动

```bash
cd tools/agent_diagnose

# 本地开发（127.0.0.1:8000，--reload）
uv sync && ./run_diagnose.sh

# 远端 / 云服务器（0.0.0.0:8000，nohup 后台，pid → .diagnose.pid，log → diagnose.log）
./serve_remote.sh 8000
```

### Agent 命名规范（重要）

- **baseline** —— 原始 baseline（react + JSON action）
- **baseline_v\*** —— 在 baseline 之上修补问题的迭代（CodeAct + 超参，譬如 baseline_v1）
- **agent_v\*** —— 架构换代后的版本（agent_v0 = 架构重写第 0 版，未来 agent_v1, agent_v2 ...）

完整顺序见 [tools/agent_diagnose/src/agent_diagnose/config.py](tools/agent_diagnose/src/agent_diagnose/config.py) 的 `AGENT_KIND_ORDER`，新版本只在这里加一行就能让表格 / 卡片 / 矩阵 / 颜色族自动跟上。

### `/overview` —— 跨 agent 看大盘

仅展示**完整跑完 50 题**的 run，半成品自动隐藏。三段：

1. **各次运行核心指标** —— 表格：智能体 / 运行实例 / 题数 / 微观分 / 宏观分 / 提交率 / 错误步率 / 平均步数 / 难度均分（4 列）。表头 `ⓘ` 鼠标悬停看每个指标的算法定义。
2. **各类智能体核心指标对比（多 seed 均值）** —— 每个 agent_kind 一张五维卡，纵向堆叠（baseline → baseline_v\* → agent_v\*），跨档 ▲ 进步 / ▼ 退步箭头一眼可见架构升级带来的相对变化。
3. **逐题得分矩阵** —— 列按 **agent_kind 聚合多 seed 均值**（不是逐 run 列，避免横向溢出），单元格 `×N` 标记参与平均的 seed 数。chip 切 `regressions / improvements / both_zero / disagreements` 筛 (HTMX 局部刷新)。点击跳单题回放，链接到该 kind 的"代表 run"。

### `/task/<id>?run=<run_id>` —— 单题单 run 五栏回放

- **题目卡** —— question / 难度 / score / elapsed / steps / v0 路由分支 / shape_spec / plan，knowledge.md 折叠原文。
- **左侧粘性 step 时间轴** —— 锚点跳转，每条带 ok/fail/submit 色块。
- **右主区每步五栏（按 LLM 思考时序自上而下）**：
  1. **① Intent** —— 自动抽取的"这步要做什么"（baseline `thought` / 代码顶部 `# 注释` / 启发式 `pd.read_csv` / `groupby` / `submit` 等）
  2. **② LLM Input** —— *诊断层重建*的 messages（折叠多条），`system / user (task) / assistant (step n) / user (obs n)` 角色染色。诊断层导入 baseline / v0 prompt builders 回放，**不依赖 agent 端埋点**；标 `ⓘ reconstructed`
  3. **③ LLM Output** —— `raw_response` 中切出的 *Thinking 散文 + 代码顶部注释*（紫色斜体框）+ 折叠原始 raw response
  4. **④ Code** —— Prism Python 高亮 + Copy 按钮
  5. **⑤ Execution Result** —— stdout / stderr 横排两列，错误步红框聚焦
- **底部 `prediction.csv` vs `gold.csv`** —— 列 multiset diff（matched / extra / missing），与 scorer 同口径

### `/eval` —— enhanced_eval 报告对比

读 `reports/<version>_eval_report.json`，base / challenger 双卡 + 自动 markdown diff，覆盖 EVAL_PLAN_30D §1 全部五类指标（accuracy / distribution / submission / consistency / failure_clusters）。

### 数据源 / 边界

仅读 `<package>/artifacts/runs/<run_id>/task_*/{trace.json, prediction.csv}` + `reports/<run_id>_scored.json`，**不改 baseline / v0 / scorer**。LLM Input 重建走诊断层，agent 端 0 改动。

下版本：同题多 run 并排 + 人工 step 标注（`labels.jsonl` append-only）。

---

## 文档导览

- 评测协议、列 multiset 比对的精确定义 → [docs/比赛简介.md](docs/比赛简介.md)
- 2024–2026 相关工作综述（CodeAct / GEPA / DS-STAR / RSL-SQL / HEAR / AdaDocVQA）→ [docs/方案调研综述.md](docs/方案调研综述.md)
- 4 层改进路线 + 主流 agent 架构对比 → [docs/改进路线图.md](docs/改进路线图.md)
- 30 天评测方法 (5 类指标 / 3 seed / diff 阈值) → [docs/EVAL_PLAN_30D.md](docs/EVAL_PLAN_30D.md)
- Docker 打包 5 红线 + 子进程 / SIGALRM / max_retries 设计 → [docs/DOCKER_PACKAGING.md](docs/DOCKER_PACKAGING.md)
- Baseline 架构图 + 失败模式分析 → [reports/baseline_architecture.html](reports/baseline_architecture.html)

---

## 致谢

- Starter-kit：[HKUSTDial/kddcup2026-data-agents-starter-kit](https://github.com/HKUSTDial/kddcup2026-data-agents-starter-kit)
- 后端 LLM：[Qwen3.5-35B-A3B](https://qwenlm.github.io/) (Apache 2.0)
- 评测框架参考：DABench (arXiv:2407.15838)

## License

MIT（评测代码与文档）。Starter-kit 子目录遵循其原始 license。
