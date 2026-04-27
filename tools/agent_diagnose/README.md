# Agent Diagnose

KDD Cup 2026 data agent 诊断面板 — 跨 run 对比 + 单题回放。FastAPI + Jinja2 + HTMX，零外网依赖。

## 启动

```bash
cd tools/agent_diagnose
./run_diagnose.sh                 # uvicorn :8000，开发模式 --reload
# 或显式：
uv run agent-diagnose --host 0.0.0.0 --port 8000
```

浏览器开 http://localhost:8000 跳转到 `/overview`。

## 功能

- **`/overview`**：所有 run 的 KPI（micro/macro/提交率/错误步率） + 50 题 × N run 的 score 矩阵，可筛选 regressions / improvements / both_zero / disagreements
- **`/task/{task_id}?run=<run_id>`**：单题单 run 的完整 step 时间轴，每步含 raw_response / code / observation；底部 prediction.csv vs gold.csv 列 multiset diff

## 数据源（只读，不修改）

- baseline runs：`../../kddcup2026-starter-kit/artifacts/runs/`
- v0 runs：`../../data_agent_v0/artifacts/runs/`
- scored.json：`../../reports/<run_id>_scored.json`（缺则自动调 `src/eval/scorer.py:score_batch` 现算）
- 题目 + gold：`../../data/demo/public/{input,output}/task_<id>/`
