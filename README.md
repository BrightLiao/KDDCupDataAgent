# KDD Cup 2026 — Data Agents 参赛仓库

针对 [KDD Cup 2026 Track: Data Agents for Complex Data Analysis](https://dataagent.top/) 的方案、基线复跑、评测与文档。

> 比赛任务：给定一个数据科学问题（自然语言）+ 一组多模态数据资产（CSV / SQLite / JSON / 文档），agent 需自主探索、推理、产出表格答案 `prediction.csv`。
> 评分：`Score = Recall − λ · (Extra Columns / Predicted Columns)`，列以 multiset 比对（忽略列名 / 行序），λ=0.5。

---

## 当前进度（2026-04-25）

| 指标 | 值 | 说明 |
|---|---|---|
| Micro Mean Score | **0.5153** | 50 题平均，列 multiset 比对 |
| Macro Mean Score | **0.4022** | 先按难度求均，再均值 |
| 提交率 | 80% (40/50) | 输出 `prediction.csv` 的任务比例 |
| 主 bottleneck | 33.7% 错误步 | ReAct 严格 JSON action 解析失败死循环 |

按难度：Easy 0.58 · Medium 0.52 · Hard 0.51 · Extreme 0.00。详见 [`reports/baseline_architecture.html`](reports/baseline_architecture.html)。

后端 LLM：Qwen3.5-35B-A3B（阿里云百炼，OpenAI 兼容 API）。

---

## 目录结构

```
.
├── docs/                            # 方案文档（中文）
│   ├── 比赛简介.md                   # 题型、评分、难度划分
│   ├── 方案调研综述.md                # 2024-2026 SOTA 综述（CodeAct / GEPA / DS-STAR / RSL-SQL ...）
│   └── 分难度方案设计.md              # 4 档难度的分支方案 + 角色周计划
│
├── kddcup2026-starter-kit/          # 官方 starter-kit 的本地 fork（已加 retry + patch）
│   ├── src/data_agent_baseline/    #   ReAct agent + 8 个 tool
│   ├── configs/react_baseline.local.yaml   # API key 占位（gitignored）
│   ├── run_baseline.sh             # 注入 BAILIAN_API_KEY 后跑 baseline
│   └── run_retry.sh                # max_steps=30 / timeout=1200s 重试失败任务
│
├── src/eval/scorer.py              # 自实现评分器（列 multiset 对齐 §6.5/§7.1）
├── scripts/
│   ├── profile_demo.py             # 扫描 demo 数据集，导出 reports/demo_profile.md
│   └── convert_bird.py             # BIRD (arXiv:2305.03111) → KDD task 格式（外部验证集）
│
├── reports/
│   ├── baseline_architecture.html  # 50 题实跑结果 + 架构图 + Agent/Tool 详解
│   ├── baseline_scored.json        # 评分器输出（per-task 明细）
│   └── demo_profile.md             # demo 数据集统计
│
├── config/                         # 云资源 key（*.pem 已 gitignore）
└── data/                           # demo 数据集（gitignore，~2.2G）
```

---

## 快速开始

### 1. 准备环境

```bash
git clone <this-repo> KDDCupDataAgent
cd KDDCupDataAgent

# Python 依赖（推荐 uv）
cd kddcup2026-starter-kit
uv sync
cd ..
```

### 2. 配置 API key

在仓库根目录新建 `.env`（已 gitignore）：

```bash
BAILIAN_API_KEY=sk-xxxx   # 阿里云百炼 (https://bailian.console.aliyun.com)
```

`run_baseline.sh` 会在运行时把 key 注入到 `configs/react_baseline.local.yaml`。

### 3. 准备数据

把 demo 数据集解压到 `data/demo/public/`（路径需与 [`kddcup2026-starter-kit/configs/react_baseline.local.yaml`](kddcup2026-starter-kit/configs/react_baseline.local.yaml) 中的 `dataset.root_path` 一致）。

```
data/demo/public/
├── input/task_<id>/      # 每题的 question + context 数据
└── output/task_<id>/gold.csv   # gold answer
```

### 4. 跑 baseline

```bash
cd kddcup2026-starter-kit
./run_baseline.sh run-benchmark           # 全量 50 题
# 或
./run_baseline.sh run-task task_11        # 单题
```

产物：`kddcup2026-starter-kit/artifacts/runs/<run_id>/task_<id>/{trace.json, prediction.csv}`。

### 5. 评分

```bash
cd ..   # 回到仓库根目录
uv run python src/eval/scorer.py \
    --predict-root kddcup2026-starter-kit/artifacts/runs/demo_qwen35_baseline \
    --gold-root data/demo/public/output \
    --input-root data/demo/public/input \
    --out reports/baseline_scored.json
```

输出 micro / macro mean Score + 按难度分布。

### 6. 重试失败任务（可选）

如有 `Agent did not submit` 或 timeout 失败，可单独提步数 + 时长重跑：

```bash
cd kddcup2026-starter-kit
./run_retry.sh task_19 task_250 task_396 ...
```

---

## 文档导览

- 评测协议、列 multiset 比对的精确定义 → [`docs/比赛简介.md`](docs/比赛简介.md)
- 2024–2026 相关工作综述（CodeAct / GEPA / DS-STAR / RSL-SQL / HEAR / AdaDocVQA）→ [`docs/方案调研综述.md`](docs/方案调研综述.md)
- 分难度方案 + 团队周计划 → [`docs/分难度方案设计.md`](docs/分难度方案设计.md)
- Baseline 架构图 + 失败模式分析 → [`reports/baseline_architecture.html`](reports/baseline_architecture.html)

---

## 已识别的下一步优化（按 ROI 排序）

1. **ReAct → CodeAct**（arXiv:2402.01030）：直接出 ` ```python ` 代码块，绕开 JSON action_input 三引号转义陷阱，预计消灭 33.7% 错误步 + 救回 10 个未提交任务
2. **输出归一化器**：submit 前强制 `round(2)` / ISO 日期 / 空值统一，对齐 `src/eval/scorer.py:38` 的 `normalize_value`
3. **Schema 预览注入 prompt**：启动时跑一次 `head -3 + dtypes`，省 4–6 步预算
4. 留 15 个 holdout 做反过拟合对照
5. 跑 DABench 公开版 257 任务做外部验证集（避免在 50 题 demo 上过拟合）

---

## 致谢

- Starter-kit：[HKUSTDial/kddcup2026-data-agents-starter-kit](https://github.com/HKUSTDial/kddcup2026-data-agents-starter-kit)
- 后端 LLM：[Qwen3.5-35B-A3B](https://qwenlm.github.io/) (Apache 2.0)
- 评测框架参考：DABench (arXiv:2407.15838)

## License

MIT（评测代码与文档）。Starter-kit 的子目录遵循其原始 license。
