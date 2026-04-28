"""L3 答案形态约束 —— 启动时让 LLM 解析 question 出 shape spec，submit 时校验。

ShapeSpec 是 picklable plain dict（在 worker 子进程内消费），不用 frozen dataclass。"""
from __future__ import annotations

import json
import re
from typing import Any

from data_agent_baseline.agents.model import ModelAdapter, ModelMessage

_SHAPE_PROMPT = """
You are parsing a data-analysis question to extract the expected answer SHAPE
(columns and at-most row count). Be CONSERVATIVE — when in doubt, output null.

Output a JSON object with these fields:

- "expected_columns": list of short snake_case strings naming each column the answer
  should have, ordered as the question asks (e.g., ["patient_id", "diagnosis"]).
  Use the actual schema field names (or close synonyms) — DO NOT collapse multiple
  schema fields into a single semantic column:
    * Question says "full name" and schema has `first_name` + `last_name`
      → output ["first_name", "last_name"]  (two columns, NOT one "full_name")
    * Question says "score" but schema field is named `goal` → output ["goal"]
  When `knowledge.md` provides exemplar SQL or example queries, the SELECT clause
  there is authoritative — match its column count and ordering literally.
  If the question is ambiguous about exact column count, output null. Do not
  include columns the question doesn't ask for.

  AVOID these common over-reaches:
    * Foreign-key fields: schema columns named `*_id`, `link_to_*`, `*_ref` are
      pointers, NOT semantic answers. Question "what's X's major?" and schema
      has `link_to_major` (FK to majors table) → output ["major_name"] (the
      target's actual name field), NOT ["link_to_major"]. The plan must follow
      the link to get the human-readable value.
    * Implicit subjects from pronouns: question "give their consumption" or
      "their height" — the pronoun "their" refers back to a subject already
      filtered (e.g., specific people). Do NOT add a subject column like
      `customer_id` or `name` unless the question explicitly says "list X and
      their Y" or "for each X, the Y". Singular questions about a filtered
      group only ask for the metric, not the subject.
    * Tally / count adverbs without explicit grouping: "tally the X" or "count
      the X" usually means return the X values themselves (as a multiset, with
      duplicates indicating frequency) rather than a (X, count) two-column
      aggregate. Only output a `count` column when the question explicitly
      says "for each X give its count" or "X with frequency / occurrences".

- "expected_row_count": an integer ONLY when the question explicitly states a numeric
  cap, like "top 5", "the 3 largest", "5 most recent", "first 10". Examples:
    * "list the top 5 customers" → 5
    * "find the 3 oldest patients" → 3
    * "list patients with severe thrombosis" → null (no numeric cap)
    * "state the date X paid dues" → null (singular phrasing does NOT imply count=1; the data may have multiple matching records, and column-multiset scoring rewards finding all of them)
    * "find the first record" → null (unless data clearly is unique-by-construction)
  When uncertain, output null. Singular English phrasing ("the date", "the value")
  must NOT be interpreted as count=1 unless the question explicitly says so.

- "row_count_kind": one of:
    * "at_most" if expected_row_count comes from "top N" / "first N" phrasing
    * "all_matching" if the question implies "find all that match" (most cases)
    * null if expected_row_count is null
  Never use "exact" — it's too strict and harms recall when the data has more matches.

- "notes": optional one-sentence English explanation. Can be empty.

Output exactly one fenced ```json ... ``` block. No other text.

## Question

{question}
{schema_section}{knowledge_section}
""".strip()

_FENCE_RE = re.compile(r"```json\s*\n?(.*?)```", re.DOTALL)


def extract_shape_spec(
    question: str,
    model: ModelAdapter,
    *,
    knowledge_md: str | None = None,
    schema_summary_text: str | None = None,
) -> dict[str, Any]:
    """单次 LLM 调用提取形态约束。失败时返回 fail-open 空 spec。

    knowledge_md / schema_summary_text 当非空时会注入 prompt，帮助消歧
    （如 "full name" → 多列 / 字段名错配）。两者都为 None 时退回旧行为（仅看 question）。
    """
    prompt = _SHAPE_PROMPT.format(
        question=question.strip(),
        schema_section=_render_section("Schema fields (column names that appear in data)", schema_summary_text),
        knowledge_section=_render_section("Domain knowledge (from knowledge.md and doc/*.md)", knowledge_md),
    )
    try:
        raw = model.complete([ModelMessage(role="user", content=prompt)])
    except Exception as exc:  # noqa: BLE001
        return _empty_spec(error=f"llm_call_failed: {exc}")

    m = _FENCE_RE.search(raw)
    payload_text = m.group(1).strip() if m else raw.strip()
    try:
        payload = json.loads(payload_text)
    except Exception as exc:  # noqa: BLE001
        return _empty_spec(error=f"json_parse_failed: {exc}", raw=raw[:200])

    if not isinstance(payload, dict):
        return _empty_spec(error="not_a_json_object", raw=raw[:200])

    return _parse_shape_spec(payload)


def _parse_shape_spec(payload: dict[str, Any]) -> dict[str, Any]:
    """从 LLM 返回的 dict 中规整 shape_spec 字段，强制 row_count_kind 一致性。

    供 extract_shape_spec 与 planner.create_plan_with_shape 共用 —— 两者输出格式相同，
    只是合一调用把 shape_spec 嵌在更大的 JSON 对象里。
    """
    expected_columns = payload.get("expected_columns")
    if expected_columns is not None:
        if isinstance(expected_columns, list) and all(isinstance(c, str) for c in expected_columns):
            expected_columns = [c.strip() for c in expected_columns if c.strip()]
            if not expected_columns:
                expected_columns = None
        else:
            expected_columns = None

    expected_row_count = payload.get("expected_row_count")
    if not isinstance(expected_row_count, int) or expected_row_count <= 0:
        expected_row_count = None

    row_count_kind = payload.get("row_count_kind")
    if row_count_kind not in ("at_most", "all_matching"):
        row_count_kind = None
    # Force at_most semantics when count is set — never enforce "exact"
    if expected_row_count is not None and row_count_kind is None:
        row_count_kind = "at_most"
    if row_count_kind == "all_matching":
        expected_row_count = None  # all_matching has no numeric cap

    notes = payload.get("notes")
    if not isinstance(notes, str):
        notes = ""

    return {
        "expected_columns": expected_columns,
        "expected_row_count": expected_row_count,
        "row_count_kind": row_count_kind,
        "notes": notes,
        "error": None,
    }


def validate_submit(
    columns: list[str],
    rows: list[list[Any]],
    spec: dict[str, Any] | None,
) -> tuple[bool, str | None, dict[str, Any]]:
    """
    返回 (ok, error_msg, info)。

    - 列数与 spec.expected_columns 长度不等 → 拒绝，回喂 LLM 让它修
    - row_count_kind=='exact' 且行数不等 → 拒绝
    - row_count_kind=='at_most' 且行数超 → 截断（info['truncated_to'] 记录）
    - 其他 → 通过

    info 总是返回，包含 truncated_to / observed_columns / observed_rows 等便于 trace。
    """
    info: dict[str, Any] = {
        "observed_columns": len(columns),
        "observed_rows": len(rows),
    }
    if not spec or not spec.get("expected_columns"):
        return True, None, info

    expected_cols = spec["expected_columns"]
    info["expected_columns"] = expected_cols

    if len(columns) != len(expected_cols):
        msg = (
            f"submit() rejected: expected {len(expected_cols)} column(s) "
            f"({expected_cols}) but got {len(columns)} ({columns}). "
            "Adjust your DataFrame and call submit() again."
        )
        return False, msg, info

    expected_n = spec.get("expected_row_count")
    kind = spec.get("row_count_kind")
    if expected_n is not None and kind == "at_most" and len(rows) > expected_n:
        rows[:] = rows[:expected_n]
        info["truncated_to"] = expected_n

    info["observed_rows"] = len(rows)
    return True, None, info


def _render_section(title: str, body: str | None) -> str:
    """优雅拼接 prompt 节：body 非空时拼 '\\n\\n## {title}\\n\\n{body}'，否则空字符串。"""
    if not body or not body.strip():
        return ""
    return f"\n\n## {title}\n\n{body.strip()}"


def _empty_spec(*, error: str | None = None, raw: str | None = None) -> dict[str, Any]:
    return {
        "expected_columns": None,
        "expected_row_count": None,
        "row_count_kind": None,
        "notes": "",
        "error": error,
        "raw": raw,
    }
