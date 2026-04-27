# Data Agent v0

按 [改进路线图 L1–L4](../docs/改进路线图.md) 重写的数据 agent，与 baseline (`kddcup2026-starter-kit/`) 并列，共用 `src/eval/scorer.py` 和 `data/demo/public/` 数据集，可直接做 A/B 对照。

## 优化点

- **L1 协议**：CodeAct ` ```python ``` ` 代码块代替 ReAct JSON action_input
- **L2 上下文**：runner 启动时全量预扫 `context/{csv,json,db,doc,knowledge.md}`，对象预加载到 REPL 命名空间，schema 摘要 + knowledge 全文注入 system prompt
- **L3 答案控制**：`submit()` 内部走 shape spec 校验 + 与 scorer 共享 `normalize_value`
- **L4 架构**：difficulty router — Easy/Medium 走 flat CodeAct (max_steps=8)，Hard/Extreme 走 Plan-Executor with Replan（连续 3 步同错触发 replan，5 次 replan 强制 best-effort submit）

## 快速开始

```bash
cd data_agent_v0

# 准备 .env（仓库根目录）：BAILIAN_API_KEY=sk-...
./run_v0.sh status                        # 检查配置
./run_v0.sh run-task task_11              # 单题
./run_v0.sh run-benchmark --limit 5       # 子集
./run_v0.sh run-benchmark                 # 全量 50 题
```

产物：`artifacts/runs/<run_id>/task_<id>/{trace.json, prediction.csv}`，trace 字段比 baseline 多 `plan` / `replan_events` / `shape_spec`。

## 评分（沿用 baseline 同款 scorer）

```bash
cd ..
uv run python src/eval/scorer.py \
    --predict-root data_agent_v0/artifacts/runs/<run_id> \
    --gold-root data/demo/public/output \
    --input-root data/demo/public/input \
    --out reports/v0_scored.json
```

## 工具能力（暴露方式变了，类型不变）

REPL 命名空间下可直接调用：`read_csv` / `read_json` / `read_doc` / `list_context` / `inspect_db` / `run_sql` / `inspect` / `submit`。L2 已自动预加载 `df_<filename>` / `json_<filename>` / `conn_<dbname>`，第一步代码就能直接用。
