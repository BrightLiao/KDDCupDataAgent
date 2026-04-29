# 版本迭代记录

KDD Cup 2026 Data Agent 参赛代码每次迭代的目标 / 改动 / 3-seed 验证结果。命名规范见 [tools/agent_diagnose/src/agent_diagnose/config.py](../tools/agent_diagnose/src/agent_diagnose/config.py) 的 `AGENT_KIND_ORDER`：

- `baseline` —— 原始 baseline（react + JSON action）
- `baseline_v*` —— 在 baseline 上修补问题的迭代（不改架构）
- `agent_v*` —— 架构换代后的版本

> 验证口径：**3 seed × 50 demo 题**（seed=no_seed / 42 / 43），`scripts/run_3seed_eval.sh` 跑全 + `src.eval.enhanced_eval` 聚合。所有数字来自 `reports/<version>_eval_report.json`，不是单 seed 数。

---

## 总览

| 版本 | micro | macro | perfect | zero | sub_rate | 3-seed 全一致 | 报告 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| baseline | 0.3756 | 0.3268 | 7 / 50 | 21 | 80% | 9 / 50 | [baseline_3seed_remote_eval_report.json](../reports/baseline_3seed_remote_eval_report.json) |
| baseline_v1 | 0.5845 | 0.4362 | 22 / 50 | 12 | 94% | 26 / 50 | [baseline_v1_3seed_remote_eval_report.json](../reports/baseline_v1_3seed_remote_eval_report.json) |
| agent_v0 | 0.5852 | 0.4334 | 22 / 50 | 14 | 94% | **31 / 50** | [v0_3seed_remote_eval_report.json](../reports/v0_3seed_remote_eval_report.json) |
| **agent_v0_tuned** | **0.6267** | **0.4603** | **23 / 50** | **12** | 94% | 25 / 50 | [v0_v5_F1F2tuned_3seed_eval_report.json](../reports/v0_v5_F1F2tuned_3seed_eval_report.json) |

```text
micro 演进:  0.376  →  0.585  →  0.585  →  0.627
        baseline   baseline_v1  agent_v0   v0+F1F2
            +0.21       +0.00     +0.04
```

---

## 1. baseline（起点）

**时间**：2026-04-25（[`1aa9750`](https://github.com/BrightLiao/KDDCupDataAgent/commit/1aa9750) 初始提交）

**目标**：跑通 starter-kit 给的 ReAct agent，建基线。

**架构**：

- ReAct loop：每步 LLM 输出严格 JSON `{thought, action, action_input}`
- 4 个工具：`list_context` / `read_csv` / `run_sql` / `answer`
- 单进程，无 REPL，无 plan，无 shape 校验
- max_steps=16

**3-seed 结果**：

| 指标 | 值 |
| --- | --- |
| micro | 0.3756 |
| macro | 0.3268 |
| n_perfect | 7 / 50 |
| n_zero | 21 / 50 |
| sub_rate | 80%（10/50 没成功提交） |
| consistency | 3 seed 全一致仅 9 / 50 |

按难度：easy 0.428 / medium 0.377 / hard 0.336 / extreme 0.167。

**主要失败模式**：max_steps 不够走完探索 + answer；列名 / shape 错；CSV 读不进；JSON action 解析失败。

---

## 2. baseline_v1 — 超参修补（CodeAct 接入）

**时间**：2026-04-27（[`77c752a`](https://github.com/BrightLiao/KDDCupDataAgent/commit/77c752a) / [`1b76fc1`](https://github.com/BrightLiao/KDDCupDataAgent/commit/1b76fc1)）

**目标**：在 baseline 上不动架构，先把"题没跑完 / 跑超时 / 大文件读不进"这三类失败修掉。

**改动**：

- 把 baseline 的 ReAct loop 替换成 `data_agent_v0.executor.CodeActExecutor`（CodeAct 协议：LLM 输出 ` ```python ``` ` 块代替 JSON action）
- 共享 v0 的 L2 preload（preload csv/json/sqlite 进 REPL namespace）
- 超参三件套：
  - `max_steps`：16 → **24**
  - `max_csv_size_mb`：500 → **100**（避免大 CSV 占内存超时）
  - `task_timeout_seconds`：600 → **900**（给 hard 题更多时间）
- `EnvModelAdapter.max_retries=0`（避免 4xx 重试浪费 budget）
- Docker 提交链路 + tini PID 1 + 子进程隔离

**3-seed 结果**：

| 指标 | 值 | vs baseline |
| --- | --- | --- |
| micro | 0.5845 | **+0.2089** |
| macro | 0.4362 | +0.1094 |
| n_perfect | 22 / 50 | +15 |
| n_zero | 12 / 50 | -9 |
| sub_rate | 94% | +14% |
| consistency | 26 / 50 | +17 |

按难度：easy 0.658 / medium 0.653 / hard 0.433 / extreme 0.000。

**最大收益来源**：CodeAct 协议 + REPL preload，让 LLM 不用每步重读文件，状态在 step 间持续。**这一档是整个项目里 micro 跳得最大的一档**（+0.21），证明"先解决工具/超参的低垂果实，再做架构"是对的顺序。

---

## 3. agent_v0 — 架构换代（plan-executor + shape spec）

**时间**：2026-04-26 ~ 2026-04-27（同 [`77c752a`](https://github.com/BrightLiao/KDDCupDataAgent/commit/77c752a) 大 commit）

**目标**：在 baseline_v1（已是 CodeAct）之上，给 hard/extreme 题加显式规划；给所有题加输出形态约束。

**架构（4 层）**：

- **L1 CodeAct REPL**：每题 spawn 一个 worker 子进程，持久 `pd / np / json / sqlite3 / Path / submit`，跨步共享 namespace（[repl.py](../data_agent_v0/src/data_agent_v0/repl.py)）
- **L2 preload**：开场把 `context/{csv,json,db}` 全部加载成 `df_<name>` / `json_<name>` / `conn_<name>`（[preload.py](../data_agent_v0/src/data_agent_v0/preload.py)）
- **L3 shape spec**：开场 LLM call 解析 question 出 `{expected_columns, expected_row_count, row_count_kind}`；submit 时守卫校验列数（[output/shape.py](../data_agent_v0/src/data_agent_v0/output/shape.py)）
- **L4 plan-executor**：hard / extreme 难度路由进 plan-executor 分支，单独 LLM call 出 5 步 plan，连续 N 步同 error 触发 replan（[orchestrator.py](../data_agent_v0/src/data_agent_v0/orchestrator.py)、[planner.py](../data_agent_v0/src/data_agent_v0/planner.py)）
- 5 大类指标 (accuracy / distribution / submission / consistency / failure_clusters) 的 enhanced_eval 评测器

**3-seed 结果**：

| 指标 | 值 | vs baseline_v1 |
| --- | --- | --- |
| micro | 0.5852 | +0.0007 |
| macro | 0.4334 | -0.0028 |
| n_perfect | 22 / 50 | 0 |
| n_zero | 14 / 50 | +2 |
| sub_rate | 94% | 0 |
| consistency | **31 / 50** | **+5** |

按难度：easy 0.582 / medium 0.694 / hard 0.458 / extreme 0.000。

**结果解读**：micro 持平于 baseline_v1，但 **3-seed 全一致从 26 提升到 31（+5）**——架构带来的稳定性收益没体现在分数上，但确实让答案在 seed 间更可重复。 hard 题分数稍升（0.433 → 0.458）；medium 题升（0.653 → 0.694）；**问题暴露在 shape extractor 上**：诊断面板分析 8/79 题 shape 列数与 gold 不一致（列名歧义类，如 "full_name" vs `[first_name, last_name]`），全部拿 0 分。

---

## 4. agent_v0 v5 F1F2tuned — shape/plan 合一 + knowledge 完整注入

**时间**：2026-04-28 ~ 2026-04-29（[`9282754`](https://github.com/BrightLiao/KDDCupDataAgent/commit/9282754) + [`26a23c8`](https://github.com/BrightLiao/KDDCupDataAgent/commit/26a23c8) prompt tuning）

**目标**：

1. F1 — 把 knowledge.md 与 schema 喂给 shape extractor，修列名歧义类系统性错误（8/79 → 目标 ≤ 3）
2. F2 — planner 喂的 knowledge cap 1500 → 8000，按 `\n## ` 章节切，恢复被砍掉的 73% 内容
3. **F1+F2 合并**：shape extractor 与 planner 输入完全重叠，合一 LLM 调用同时输出 shape+plan（节省 ~3000 input tokens / hard 题）

**改动**：

- [output/shape.py](../data_agent_v0/src/data_agent_v0/output/shape.py)：`extract_shape_spec` 加 `knowledge_md / schema_summary_text` 参数；`_SHAPE_PROMPT` 加 schema/knowledge 节 + 列名歧义规则；抽 `_parse_shape_spec(payload_dict)` 公共函数
- [planner.py](../data_agent_v0/src/data_agent_v0/planner.py)：新 `_INITIAL_PLAN_AND_SHAPE_PROMPT` 模板（合一）；`Planner.create_plan_with_shape()` 单次 LLM 调用同时出 shape+plan；抽 `_parse_plan_list` 公共函数
- [repl.py](../data_agent_v0/src/data_agent_v0/repl.py)：`shape_spec` 改可选 + 新增 `set_shape_spec(spec)` 方法 + worker 端 `op="set_shape_spec"` 命令处理（允许 REPL 起来后从主进程动态注入 spec）
- [orchestrator.py](../data_agent_v0/src/data_agent_v0/orchestrator.py)：`run()` 顺序重排 — 先开 REPL 拿 schema+knowledge → 难度路由调 LLM 算 shape(+plan) → `repl.set_shape_spec` 注入；`_render_knowledge_short` → `_render_knowledge_full`，cap 1500 → 8000，按章节切（不 mid-sentence 截）

**Prompt over-reach 防御（[`26a23c8`](https://github.com/BrightLiao/KDDCupDataAgent/commit/26a23c8) 第二轮 tuning）**：

第一次跑 single-seed 发现新 prompt 引入 3 个新错（task_180 / task_349 / task_379），都是 shape extractor 过度读 schema：

- 外键字段 `*_id` / `link_to_*` / `*_ref` 被当成答案列 → 加规则 "FK 字段是指针不是答案，plan 必须 follow link 取实际语义列"
- 代词 "their X" 被当成需要主语列 → 加规则 "pronouns don't make new columns unless explicit"
- "tally / count" 副词被当成需要 count 列 → 加规则 "tally usually means multiset row expansion, not (X, count) aggregate"

**3-seed 结果**：

| 指标 | 值 | vs agent_v0 |
| --- | --- | --- |
| micro | 0.6267 | **+0.0415** |
| macro | 0.4603 | **+0.0269** |
| n_perfect | 23 / 50 | +1 |
| n_zero | 12 / 50 | -2 |
| sub_rate | 94% | 0 |
| consistency | 25 / 50 | **-6** ⚠️ |

按难度：easy 0.659 (**+0.077**) / medium 0.740 (**+0.047**) / hard 0.442 (-0.017) / extreme 0.000。

按数据类型（特别有意思）：

| 类型 | 改前 | 改后 | Δ |
| --- | ---: | ---: | ---: |
| db | 0.333 | 0.667 | **+0.333** |
| json | 0.396 | 0.583 | **+0.188** |
| csv | 0.375 | 0.444 | +0.069 |
| mixed | 0.660 | 0.676 | +0.015 |

**结果解读**：

- ✅ accuracy 稳定提升 micro +0.04 / macro +0.03（50 题 ±8% 噪声边界，但配合 perfect+1 / zero-2 / 难度全面正向 / db 类大涨 pattern 不像偶然）
- ✅ shape 列名歧义类**几乎全修好**：task_19 +1.00 / task_283 +1.00 / task_27 +0.92 / task_355 +0.58 / task_243 +0.38 / task_408 +0.33 / task_269 +0.33 / task_199 +0.33 / task_173 +0.33（9 题大幅正向）
- ✅ **db / json 类大幅提升**（+0.33 / +0.19）—— 印证 F1 设计：把 schema 字段名 / knowledge.md 完整注入对结构化数据题作用最大
- ⚠️ **3-seed consistency 下降 -6**：新 prompt 让某些题在 LLM 抖动下更敏感（5 题 ≥ -0.30 的 top regression 大多是同 shape 不同 value 类的随机变异）。说明 prompt 改动让"模型对 prompt 措辞敏感性"上升
- ⚠️ hard 题轻微反弹 -0.017（在噪声内）

**单 seed vs 3-seed 校准**：第一次单 seed s43 评测显示 micro +0.1248，但 3-seed 校准下来真实收益是 +0.0415。**单 seed 评测会过度放大改动信号约 3 倍**，未来 prompt 改动一定要走 3-seed 验收。

---

## 待做（下一轮候选）

按 plan 文件 [`/Users/brightliao/.claude/plans/giggly-yawning-platypus.md`](file:///Users/brightliao/.claude/plans/giggly-yawning-platypus.md) 留下的两块：

- **F3 — Plan prompt 升级 + schema 描述增强**：schema_summary 携带 dtype + 样本值，planner prompt 强制 plan step 含具体表名 / 字段名 / 过滤值
- **F4-a — Executor 显式跟 plan 进度**：每 turn prompt 注入 "Step N of M: <desc>; success: <criterion>; previously completed: 1..N-1"；StepRecord 加 `plan_step_index` 字段
- **F4-b — success_criterion 自动验收**：每步后单独 LLM judge call 判断 criterion 是否达成；语义触发 replan（替代当前的 error_signature 字符串重复触发）

实施前需要先解决本轮暴露的 **3-seed consistency 下降** 问题——hard 题在某些 seed 上仍然不稳定，意味着下一轮主战场应该是"减少 prompt 措辞敏感性 / 提升 hard 题稳定性"，不是堆架构。

---

## 评测 / 复现

```bash
# 全 50 题 3-seed eval（任何 agent 通用）
./scripts/run_3seed_eval.sh \
    --agent-dir data_agent_v0 \
    --run-script run_v0.sh \
    --config configs/v0.local.yaml \
    --run-id-base demo_qwen35_v0_v5_F1F2tuned \
    --version-id v0_v5_F1F2tuned_3seed \
    --diff-base reports/v0_3seed_remote_eval_report.json \
    --skip-done

# 已跑过的 run 用 --skip-done 复用，不会重复跑
# 产物：reports/<version_id>_eval_report.json + 自动 diff markdown
```

诊断面板查看每次 run 的 trace / prompt / step 五栏：

- 本地 dev：`cd tools/agent_diagnose && ./run_diagnose.sh`
- 公网部署：<http://47.113.144.141:8000/overview>
