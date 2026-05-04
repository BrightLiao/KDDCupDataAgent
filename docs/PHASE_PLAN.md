# Phase Plan — KDD Cup 2026 Data Agents

> 单一真相源。Phase 切换时只改此文件，个人 `CLAUDE.local.<name>.md` 不变。

## Current: Phase 2 — 消除浪费 + Plan 升级

**状态**: Day 6 (2026-04-30)，Phase 1 第 6 天 | 提交配额: 2/30（待申昊提交 v2）

**当前最优版本**: agent_v0_tuned (micro 0.627, macro 0.460, perfect 23/50)

### 团队成员与分工

| 成员 | 角色 | 当前 Task | 改动范围 | 备注 |
|------|------|----------|---------|------|
| 廖老师 (brightliao) | lead | 架构 oversight + F3+ | 全局 | 指导方向，逐步交棒 |
| 申昊 (shenhao) | learning | T4 长文档摘要 + T5 长文档检索 | `preload.py` + 新增 `doc_retrieval.py` | S1: Agent 架构 + Planning |
| 王琛璋 (wangchenzhang) | learning | T1 消除探索浪费 | `data_agent_v0/.../prompts.py` (~30行) | S2: 数据与检索方向 |
| 王语萌 (wangyumeng) | learning | T2 Plan 具体化 + T3 Plan 进度跟踪 | `planner.py` + `orchestrator.py` | S3: 提示工程 + 错误分析 |

### Phase 2 Task 清单

| ID | 任务 | 改动范围 | 优先级 | 负责人 |
|----|------|---------|--------|--------|
| T1 | 消除探索浪费 | `prompts.py` (~30行) | P0 | 王琛璋 |
| T2 | Plan 具体化 | `planner.py` (~50行) | P0 | 王语萌 |
| T3 | Plan 进度跟踪 | `orchestrator.py` (~80行) | P1 | 王语萌 |
| T4 | 长文档摘要 | `preload.py` (~100行) | P1 | 申昊 |
| T5 | 长文档检索 | 新增 `doc_retrieval.py` (~150行) | P2 | 申昊 |

### 下一轮候选（F3+）

- F3: Plan prompt 升级 + schema 描述增强
- F4-a: Executor 显式跟 plan 进度
- F4-b: success_criterion 自动验收

### Hands-off 规则

- **learning 角色**: 只能编辑自己 task 分配的文件；改动超出范围前须先与廖老师确认
- **contributor 角色**: 可编辑自己 task 涉及的文件 + 共享模块（`src/eval/`、`tools/`），但不能改其他人的 agent 目录
- **共享文件**（`src/eval/`、`scripts/`、`docs/`、`tools/agent_diagnose/`）：所有人可改，但改 `tools/` 前先确认

### 版本历史参考

- `docs/VERSION_HISTORY.md` — 所有版本的 3-seed 评测结果和改动记录
- 单 seed 评测不可靠（会放大信号 ~3x），prompt 改动必须走 3-seed 验收

---

## Phase 1 — 基线搭建与架构验证 ✅ (已完成)

**时间**: 2026-04-24 ~ 04-30 | 状态: 已交付 2 次提交

**目标**: 跑通基线、搭架构、修低垂果实、建评测体系

**成果**:
- baseline (micro 0.376) → baseline_v1 (0.585, +0.21) → agent_v0 (0.585) → agent_v0_tuned (0.627, +0.04)
- 架构 4 层落地: CodeAct REPL + schema preload + shape spec + plan-executor
- 3-seed 评测体系 + Docker 提交链路 + 诊断面板

### 团队成员与分工

| 成员 | 角色 | 职责 |
|------|------|------|
| 廖老师 (brightliao) | lead | 全部代码开发、架构设计、Docker 打包、3-seed 评测 |
| 申昊 (shenhao) | learning | Hidden 结果分析、Timeout/失败题排查 |
| 王琛璋 (wangchenzhang) | learning | 答案归一化排查 |
| 王语萌 (wangyumeng) | learning | Planner 低效原因排查 |

**关键教训**:
- 单 seed 评测放大信号 ~3x，prompt 改动必须 3-seed 验收
- CodeAct 协议 + REPL preload 是最大单次提升（+0.21 micro）
- 先修工具/超参低垂果实，再做架构，顺序不能反
