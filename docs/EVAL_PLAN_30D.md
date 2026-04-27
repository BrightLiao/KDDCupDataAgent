# 30 天 30 次提交评测与冲分方案

> 适用约束：本地 demo 50 条带 gold；Hidden test 每天可提交 1 次，比赛周期 30 天 ≈ 30 次提交。
> 核心原则：**Demo 评测榨信号，Hidden 提交既学又赢；任何"试一试"的提交都会在终局缺额**。

---

## 0. 设计前提

### 0.1 三个不可变约束
1. **样本稀缺**：50 条 demo 上 1-2 题波动 = 2-4% 摆幅，accuracy 单指标不可信
2. **提交稀缺**：30 天总共 30 次 hidden 提交，无法做"纯探针"奢侈品
3. **反馈延迟**：hidden 只给总分、不给 per-task 反馈，无法定向 debug 单题

### 0.2 三层评测体系
```
Layer 1: 本地 demo 50 条     — 高频，多指标，主决策来源
Layer 2: Hidden 探针提交     — 极低频（仅 3 次），建立 demo→hidden 折算系数
Layer 3: Hidden 主迭代提交   — 22 次，每次"信息+分数"双目标
```

任何单层结论都不可单独信，**至少两层一致**才能下决策。

---

## 1. Layer 1：Demo 评测机制

### 1.1 五类指标（去掉 accuracy 单指标依赖）

| 类别 | 指标 | 角色 | 决策权重 |
|---|---|---|---|
| **Consistency** | `all3_agree_count`（3 次都同答） | **主指标 1** | 高 |
| | `majority_agree_count`（≥2/3 一致） | 主指标 2 | 高 |
| | `answer_entropy_mean` | 稳定性辅助 | 中 |
| **Distribution** | `token_per_task` (mean/p50/p95/p99) | 副作用监测 | 中 |
| | `step_per_task` (mean/p50/p95) | 决策路径长度 | 中 |
| | `submit_attempts` (once / multiple) | 一次过率 | 中 |
| **Accuracy**（辅助） | overall, by_database, by_difficulty | 仅看绝对差 ≥ 8% 才作信号 | 低 |
| **Failure Clusters** | 按错误根因聚类计数 | 定性变化信号 | 高 |
| **Perturbation** | 单题扰动后仍正确率 | 过拟合红线 | 高 |

### 1.2 评测产物：`eval_report.json`

```json
{
  "version_id": "v0.3.2-fix-crlf",
  "git_commit": "abc123",
  "timestamp": "2026-04-26T10:00:00",

  "primary_consistency": {
    "runs_per_task": 3,
    "all3_agree_count": 38,
    "majority_agree_count": 47,
    "answer_entropy_mean": 0.42
  },

  "primary_distribution": {
    "token_per_task": {"mean": 8420, "p50": 6100, "p95": 22300, "p99": 41200},
    "step_per_task":  {"mean": 5.3,  "p50": 4,    "p95": 12,    "p99": 16},
    "submit_attempts": {"once": 41, "multiple": 9}
  },

  "secondary_accuracy": {
    "overall": 0.82,
    "by_database": {"financial": 0.85, "formula1": 0.71, ...},
    "by_difficulty": {"easy": 0.95, "medium": 0.78, "hard": 0.55}
  },

  "failure_clusters": {
    "schema_misunderstanding": 4,
    "exists_vs_join": 2,
    "csv_format_issue": 1,
    "timeout": 1,
    "wrong_aggregation": 1
  },

  "perturbation_set": {
    "tested_tasks": 10,
    "robust_to_perturbation": 7
  }
}
```

### 1.3 自动化 diff 报告

每次新版本跑完，与上一版对比生成 markdown：

```markdown
## v0.3.2-fix-crlf  vs  v0.3.1-baseline

🟢 Consistency 显著改善
- all3_agree: 35 → 38 (+3)         ← 强信号
- entropy:    0.51 → 0.42 (-0.09)  ← 强信号

⚠️ 分布有副作用
- token p95: 18200 → 22300 (+22%)  ← 修了某些题但拖累尾部
- step p95:  10 → 12               ← 决策路径变长

🟢 失败聚类
- csv_format_issue: 4 → 1   ← 主因被解决
- timeout: 0 → 1            ← 新出现的失败模式，需关注

🔴 扰动测试退步
- robust: 8 → 7             ← 警告：可能引入新过拟合

🟡 准确率
- overall: 0.78 → 0.82 (+4%) ← 在 50 条噪声范围内，不作主信号
```

视觉上区分 **🟢 强信号 / ⚠️ 副作用 / 🔴 红线 / 🟡 噪声**，让"在噪声范围内"显眼，避免自欺。

### 1.4 假设登记簿（每次改动前必填）

每次改动前在 `experiments/<version>.yaml` 写：

```yaml
version: v0.3.2-fix-crlf
hypothesis: >
  添加 CRLF 检测 + 自动 strip 后，4 题 CSV 格式失败应至少修好 3 题
  （task_56, task_103, task_178 high confidence；task_241 medium）
predicted_changes:
  all3_agree:    "+2 to +4"
  csv_cluster:   "4 → 0 or 1"
  other_clusters: "no change"
predicted_hidden_delta: "+1.5 to +3.0"     # 用启动期标定的 K 推算
risk:
  - "strip 可能误伤合法 trailing whitespace（监控 task_18）"
classification: hit | miss | surprise        # 跑完后填
```

**长期跟踪你自己的预测准确率**：
- ≥ 60% → 你抓到了机制，迭代决策可信
- < 30% → 你在乱试，每次涨点都可能是噪声 → 停下来重新分析

### 1.5 Smoke test 5 题

从 50 条选 5 题封存，**只看二元翻转**（对→错 / 错→对），不看比率：
- 选题原则：每数据库 1 题、覆盖至少 3 类题型、含 1 题 hard
- 任何一题从对变错 → 强制查清，不准 merge
- 这是 50 条规模下 holdout 唯一合理的形态：**回归断路器**

### 1.6 工程纪律

- **固定随机性**：seed / temperature 全部固定；consistency 跑用不同 seed
- **完整保留 trace**：每次评测的所有 reason / observation / submit 全部归档，事后可回放
- **环境隔离**：评测代码与优化代码分离，避免改评测脚本造成假涨点
- **基线锁定**：每次只改一处，多处改动并发 → 归因不可能

---

## 2. Layer 2：启动期 Hidden 探针（3 次）

### Day 1 — Baseline anchor
- 提交当前最稳版本
- **事先**写下对 hidden 分数的预测区间
- 记录：H1 / consistency C1 / accuracy A1 / 预测偏差

### Day 2 — 单点扰动探针
- 故意关掉一个明确有效的能力（如关 preload，或关 plan-executor 让 hard 题也走 flat）
- 对比 demo 跌幅 vs hidden 跌幅
- **产出折算系数 K = Δhidden / Δdemo_consistency**
- K 是后续一切预测的基础。如果 K 极不稳定（多次后波动 > 50%），说明 demo 不能代理 hidden，需重新设计评测

### Day 3 — 难度倾向初判
- 提交一个"只对 easy 题强、对 hard 题弱"的版本（或反向，看哪个 24h 内能做出）
- 与 Day 1 对比：hidden 偏向哪边 → 推断 hidden 难度分布与 demo 的偏差

**3 次后产出**：
1. Baseline 锚点
2. 折算系数 K
3. 难度分布的初步画像

够用了。题型 / 数据库分布在主迭代期靠 piggyback 学习。

---

## 3. Layer 3：主迭代期（22 次）

### 3.1 每次提交的硬门槛（5 条全过才提交）

| 检查项 | 不通过的处置 |
|---|---|
| Demo consistency 比上版 ≥ +2？ | 不提交，配额作废 |
| Failure cluster 有**定向**改善（非散乱涨跌）？ | 不提交，重新分析 |
| 能写出 hidden 分数预测（区间宽度 ≤ 8pt）？ | 没真懂这次改动，不提交 |
| 本次只改一处？ | 拆分改动到多次提交 |
| 距收尾期 ≥ 5 天 buffer？ | 进入收尾模式（见 §4） |

**配额作废 < 配额误用**。30 天里允许浪费 2-3 次配额，不允许糊涂提交。

### 3.2 每次提交的复盘（< 30 分钟，每天必做）

提交回结果后，强制写 5 行到 `submission_log.md`：

```
Day X | <version> | demo_cons: A→B | predicted hidden: P | actual hidden: H
classification: hit | miss | surprise
why: <一句话>
next hypothesis: <明天准备改什么>
piggyback_categories: [csv_format, multi_table_join]   # 本次涉及的题型，用于事后画像
```

### 3.3 紧急规则

- **连续 3 次 hidden 不涨** → 强制停 1 天，纯做 demo 分析，不提交
- **demo 大幅退步但 hidden 涨** → branch 保留但不 merge，用 1 次提交验证是不是过拟合 hidden，确认后弃用
- **改动如果 demo consistency 不涨** → 绝不消耗提交配额去赌 hidden 会涨
- **预测准确率掉到 < 40%** → 停 1 天，重新校准 K 或反思指标
- **提交配额耗用速度警戒线**：Day N 时累计提交不能超过 `3 + (N-3) × 0.85`，超过就强制减速

### 3.4 题型 / 数据库画像的 piggyback 收集

22 次主迭代提交，每次记录 `piggyback_categories`，**长期累计自然形成 hidden 对哪类改动最敏感的画像**。
不需要专门探针——题型分布是免费副产品。

---

## 4. 收尾期（最后 5 天，5 次提交）

| Day | 用途 | 改动尺度 |
|---|---|---|
| 26 | 当前最佳稳定版本，作为保底分 | 仅集成已验证有效改动 |
| 27 | 激进尝试 #1（高方差，搏一搏） | 允许较大改动 |
| 28 | 激进尝试 #2（不同方向） | 允许较大改动 |
| 29 | 收敛回稳定版本（Day 26 微调） | 仅 prompt / 参数微调 |
| 30 | 最终提交，保守选择 | 仅 prompt 微调 |

**Day 28-30 不允许架构性改动**，失败模式排查不完。
**Day 26 的版本是终极保底**——即使后续 4 次全失败，至少这个分能算最终成绩。

---

## 5. Day 0 工程准备（必须 24 小时内完成）

如果这些工程准备没就绪，30 天的节奏会崩。

### 5.1 自动化评测脚本
- [ ] `scripts/run_eval.py`：跑 demo 50 条 × 3 次 consistency，**总耗时 ≤ 30 分钟**（必须并行）
- [ ] 输出 `eval_report.json` 包含 §1.1 五类指标
- [ ] 自动 diff 上一版，生成 `eval_diff.md`（§1.3 格式）
- [ ] 失败聚类用关键词规则即可（schema_misunderstanding / exists_vs_join / csv_format_issue / timeout / wrong_aggregation / other）

### 5.2 假设与提交记录
- [ ] `experiments/` 目录存放每个 version 的 hypothesis yaml
- [ ] `submission_log.md` 用表格格式记录每次提交（Day / version / demo_cons / predicted / actual / classification / why / next）

### 5.3 Smoke test 5 题选定 + 封存
- [ ] 选题：每数据库 1 题、覆盖 3 类题型、含 1 题 hard
- [ ] 写到 `evals/smoke_test.txt`，**绝不**用作 debug 输入

### 5.4 单题扰动测试集
- [ ] 选 10 题做扰动变体（改阈值、改字段名、改 CSV 行尾）
- [ ] 写到 `evals/perturbation_set/`，与原题成对存放

### 5.5 提交流程脚本化
- [ ] `scripts/submit.sh`：git tag → 打包 → 提交 → 回填 `submission_log.md`，一键完成
- [ ] 包含强制确认：提交前打印 5 条硬门槛 checklist，回车确认每条通过才允许提交

### 5.6 配额监控
- [ ] `scripts/quota_check.py`：打印当前累计提交次数 / 剩余次数 / 是否超过警戒线
- [ ] 每天早上跑一次，输出到当天 retro 顶部

---

## 6. 反直觉规则汇总

| 规则 | 原因 |
|---|---|
| 启动期只 3 次提交，**别多** | 30 天预算下，每多 1 次探针就少 1 次冲分机会 |
| Demo accuracy 不是主指标 | 50 条噪声太大，主信号必须用 consistency |
| Hidden 涨 demo 跌的版本不能 merge | 即使分高，多半是过拟合 hidden 的某个隐藏分布 |
| 每次提交必须写预测 | 不写预测的提交，事后说不出涨/跌原因，等于浪费配额 |
| Smoke test 5 题翻转就停下来查 | binary 信号最可信，5 题之一翻转 = 出现新机制性退化 |
| 不允许并发改动 | 多处同时改 = 归因失败 = 这次提交白瞎 |
| 配额作废 < 配额误用 | 30 天里允许浪费 2-3 次，不允许糊涂提交 |
| 收尾期保留 5 次预算 | 失败模式排查需要时间，最后冒险必须有保底 |

---

## 7. 每日 mini-retro（< 30 分钟）

每天傍晚跑一遍这 5 个问题：

1. **今天 demo consistency 涨了吗？涨多少？涨在哪个 cluster？**
2. **今天提交了吗？预测对吗？classification 是 hit/miss/surprise？**
3. **失败聚类有没有出现新类别？**（出现 = 优先修）
4. **本周累计 hit 率多少？**（< 40% → 停 1 天重新分析）
5. **配额还剩多少？是否超警戒线？**

---

## 8. 周一周中 retro（额外 30 分钟）

每周一次，回看：

1. 这周哪个 cluster 修复带来 hidden 收益最大？
2. piggyback_categories 累计统计：hidden 对哪类题型最敏感？
3. 折算系数 K 是否仍稳定？需要重新标定吗？
4. 假设登记簿里 hit / miss / surprise 比例？
5. 预测 hidden 区间的覆盖率（实际值落在预测区间的比例）

---

## 9. 一句话

**30 天 30 次提交意味着每次都是小赌局，不能再有"试一试"的奢侈**。
启动期压到 3 次抓最关键的折算系数，主迭代期每次"既学又赢"，最后 5 天封禁所有冒险——这样能在稀缺预算下既拿信息又拿分数。

---

## 附录 A：Day 0 checklist 简表

```
[ ] scripts/run_eval.py + 5 类指标输出
[ ] eval_diff.md 自动生成
[ ] failure_cluster 关键词规则
[ ] experiments/ 目录 + hypothesis 模板
[ ] submission_log.md 模板
[ ] evals/smoke_test.txt（5 题封存）
[ ] evals/perturbation_set/（10 题扰动变体）
[ ] scripts/submit.sh + 强制 checklist
[ ] scripts/quota_check.py
[ ] 启动期 Day 1-3 三个版本的具体计划草稿
```

## 附录 B：30 天提交时间线速查

```
Day 1   [探针] baseline anchor                        → 折算系数初始值
Day 2   [探针] 关键能力扰动                            → 折算系数 K
Day 3   [探针] 难度倾向初判                            → 难度分布画像
Day 4-25 [主迭代] 每次「信息+分数」双目标               → 22 次
Day 26  [收尾] 当前最佳稳定版（保底分）
Day 27  [收尾] 激进尝试 #1
Day 28  [收尾] 激进尝试 #2（不允许架构改动）
Day 29  [收尾] 收敛回稳定版（仅微调）
Day 30  [收尾] 最终保守提交
```
