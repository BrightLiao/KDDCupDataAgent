# data-agent-baseline-v1

baseline + L1-L3 改进的最小消融实验包。仍然是 baseline 的扁平 ReAct 循环（无 planner、无难度路由），只把以下三个独立技术增量叠加在 baseline 之上：

- **L1 CodeAct**：固定工具（`read_csv` / `peek_csv` / `query_db` …）替换为持久 Python REPL，每步以一个 ` ```python ... ``` ` 代码块作为 action。
- **L2 schema preload + knowledge.md inject**：开 REPL 时一次性扫描 `context/{csv,json,db}/`，构造 `df_<name>` / `json_<name>` / `conn_<name>`，并把 schema 摘要 + `knowledge.md` 注入 system prompt。
- **L3 shape spec extraction**：进入 REPL 前用单次 LLM 调用解析 question，得到 `expected_columns` / `expected_row_count` / `row_count_kind`，注入 prompt + 在 `submit()` 时校验。

不在本包内的：

- L4 难度路由 / Plan-Executor / replan（保留在 `data_agent_v0/`）

复用 `data_agent_v0` 的 `repl.py`、`executor.py`、`prompts.py`、`output/shape.py`，只重写 orchestrator 与 CLI，使其退化为扁平循环。

## 用法

```bash
cd data_agent_baseline_v1
uv sync
./run_baseline_v1.sh status
./run_baseline_v1.sh run-task task_11
./run_baseline_v1.sh run-benchmark
```
