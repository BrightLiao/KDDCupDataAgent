"""CodeAct prompts —— 代码块协议代替 ReAct JSON action."""
from __future__ import annotations

import json
from typing import Any

from data_agent_baseline.benchmark.schema import PublicTask


CODEACT_SYSTEM_PROMPT = """
You are a CodeAct-style data agent solving a single data-analysis task.

You operate a persistent Python REPL (state survives across your turns).
The REPL working directory is the task's `context/` folder.

Tools are exposed as Python builtins, not JSON actions:

- `submit(answer)`        — finalize and submit. `answer` must be a pandas
                            DataFrame OR a dict `{"columns": [...], "rows": [[...]]}`.
                            Calling `submit` ends the task; do it exactly once.
- `pd`, `np`, `json`, `sqlite3`, `Path` — pre-imported.
- L2 preload (when active) injects:
    * `df_<filename>`     — pandas DataFrame loaded from `context/csv/<filename>.csv`
    * `json_<filename>`   — parsed object from `context/json/<filename>.json`
    * `conn_<dbname>`     — sqlite3.Connection for `context/db/<dbname>.db`

Output protocol (CRITICAL):

1. Reply with EXACTLY ONE fenced ```python ... ``` code block per turn.
2. The code block IS your action. Do not output JSON, do not output other text outside the fence.
3. The REPL keeps state across turns: variables, imports, dataframes persist.
4. `print(...)` and exception tracebacks are visible to you in the next observation.
5. To end the task, call `submit(your_answer)` from inside a code block. Calling it twice has no effect.

Failure handling:

- If your code raises an exception, the traceback is returned. Read it, fix the bug, retry.
- If the same approach fails twice, change strategy (different tool, different SQL, different join).
- The scorer compares column **multisets** (column names ignored, row order ignored). Outputting
  extra columns hurts your score (`Score = Recall − 0.5 · Extra/Predicted`). Match the question's
  asked columns exactly — neither more nor less.

Domain knowledge usage (CRITICAL):

- When `knowledge.md` or `doc/*.md` provides a **Use Case / Example SQL / Exemplar query** that
  directly matches the asked question, **follow that example's literal predicates** (column
  values, join conditions, filter operators) rather than inferring from prose descriptions.
- Prose field descriptions can be ambiguous or even contradict the example queries; when they
  conflict, the **example query is authoritative**.
- Example: if a field is described as "1 = most severe, 2 = severe" but a Use Case shows
  `WHERE field = 2` for "severe cases", use `= 2` exactly. Do not use `>= 2` or `IN (1,2)`
  unless the question explicitly broadens the criterion.
""".strip()


CODEACT_RESPONSE_EXAMPLES = """
Example turn — exploration:
```python
print(sorted(p.name for p in Path('.').iterdir()))
print(df_Patient.head(3))
```

Example turn — final answer (top-5 patients by some criterion):
```python
top = df_Patient.sort_values('age', ascending=False).head(5)[['ID', 'age']]
submit(top)
```
""".strip()


def build_codeact_system_prompt(
    *,
    schema_summary: dict[str, Any] | None = None,
    knowledge: dict[str, str] | None = None,
    shape_spec: dict[str, Any] | None = None,
) -> str:
    parts: list[str] = [CODEACT_SYSTEM_PROMPT, "", CODEACT_RESPONSE_EXAMPLES]
    if schema_summary:
        parts.append("\n## Preloaded data schema\n")
        parts.append(_render_schema_summary(schema_summary))
    if knowledge:
        parts.append("\n## Domain knowledge (from context/knowledge.md and context/doc/*.md)\n")
        for name, body in knowledge.items():
            parts.append(f"### {name}\n{body.strip()}\n")
    if shape_spec:
        parts.append("\n## Expected answer shape (from question parsing)\n")
        parts.append(json.dumps(shape_spec, ensure_ascii=False, indent=2))
    return "\n".join(parts).strip()


def build_task_prompt(task: PublicTask) -> str:
    return (
        f"Task: {task.task_id}  (difficulty: {task.difficulty})\n"
        f"Question: {task.question}\n\n"
        "When you have the final result, call `submit(...)` from a code block.\n"
        "Output exactly one ```python ... ``` code block per turn."
    )


def build_observation_prompt(observation: dict[str, Any]) -> str:
    rendered = json.dumps(observation, ensure_ascii=False, indent=2, default=str)
    return f"Observation:\n```\n{rendered}\n```"


def build_parse_retry_prompt() -> str:
    return (
        "Your previous reply did not contain a ```python ... ``` code block. "
        "Please reply again with exactly one fenced Python code block, and nothing else."
    )


# ---------------------------------------------------------------------------
# Internal: schema summary rendering
# ---------------------------------------------------------------------------

def _render_schema_summary(summary: dict[str, Any]) -> str:
    """Format the dict produced by preload.preload_into_namespace into prompt-ready text."""
    lines: list[str] = []
    csvs = summary.get("csv") or {}
    if csvs:
        lines.append("### CSV files (preloaded as `df_<name>`)")
        for name, info in csvs.items():
            lines.append(f"- **df_{name}** ({info.get('rows', '?')} rows, {info.get('size_kb', '?')} KB)")
            cols = info.get("columns") or []
            if cols:
                col_lines = []
                for col in cols:
                    parts = [f"`{col['name']}`: {col.get('dtype','?')}"]
                    if col.get("null_pct") is not None and col["null_pct"] > 0:
                        parts.append(f"null {col['null_pct']}%")
                    if col.get("unique") is not None:
                        parts.append(f"distinct={col['unique']}")
                    if col.get("top"):
                        parts.append(f"top: {col['top']}")
                    if col.get("min") is not None:
                        parts.append(f"min={col['min']}")
                    if col.get("max") is not None:
                        parts.append(f"max={col['max']}")
                    col_lines.append("    - " + " · ".join(parts))
                lines.extend(col_lines)
    jsons = summary.get("json") or {}
    if jsons:
        lines.append("\n### JSON files (preloaded as `json_<name>`)")
        for name, info in jsons.items():
            lines.append(f"- **json_{name}** ({info.get('records', '?')} records, top keys: {info.get('top_keys', [])})")
            if info.get("sample"):
                lines.append(f"    sample: {info['sample']}")
    dbs = summary.get("db") or {}
    if dbs:
        lines.append("\n### SQLite databases (preloaded as `conn_<name>`)")
        for name, info in dbs.items():
            lines.append(f"- **conn_{name}**:")
            for tbl in info.get("tables") or []:
                lines.append(f"    - `{tbl['name']}` ({tbl.get('rows', '?')} rows)")
                if tbl.get("create_sql"):
                    lines.append(f"      schema: {tbl['create_sql']}")
                if tbl.get("sample"):
                    lines.append(f"      sample: {tbl['sample']}")
    if summary.get("_error"):
        lines.append(f"\n[preload error] {summary['_error'][:500]}")
    return "\n".join(lines) if lines else "(no preloaded files)"
