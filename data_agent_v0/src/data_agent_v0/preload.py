"""L2 全量预扫描 —— 在 REPL worker 内执行，object 入 ns，摘要回 parent。

输入结构是固定的（KDD Cup 任务）：
    context/csv/*.csv
    context/json/*.json
    context/db/*.db        (SQLite)
    context/doc/*.md       (领域文档)
    context/knowledge.md   (出题方知识)

设计要点：
- CSV/JSON/DB 全读不截断 -> 入 ns 命名为 df_<stem> / json_<stem> / conn_<stem>
- 摘要（dtypes / describe / null率 / 类别 top / 日期 min-max / 表结构）通过 queue 回传 parent 注入 prompt
- knowledge / doc 全文读出，原样回传 parent，不入 ns
- 单 CSV 超 size cap -> 仅入 schema 不入 ns，提示 LLM 用 chunksize
"""
from __future__ import annotations

import json as _json
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

# Sentinel for unknown values in JSON-serializable summary
_UNKNOWN = "?"


def preload_into_namespace(
    context_root: Path,
    namespace: dict[str, Any],
    *,
    max_csv_size_mb: int = 500,
) -> tuple[dict[str, Any], dict[str, str]]:
    """全量预扫描。返回 (summary, knowledge)。

    summary: {"csv": {...}, "json": {...}, "db": {...}}
    knowledge: {filename: full_text}
    """
    summary: dict[str, Any] = {"csv": {}, "json": {}, "db": {}}
    knowledge: dict[str, str] = {}

    # CSV
    csv_dir = context_root / "csv"
    if csv_dir.is_dir():
        for path in sorted(csv_dir.glob("*.csv")):
            stem = _safe_var_name(path.stem)
            ns_key = f"df_{stem}"
            try:
                size_kb = path.stat().st_size / 1024
                size_mb = size_kb / 1024
                if size_mb > max_csv_size_mb:
                    summary["csv"][stem] = {
                        "loaded": False,
                        "size_kb": int(size_kb),
                        "hint": f"file > {max_csv_size_mb}MB; use pd.read_csv('{path.name}', chunksize=...) instead",
                    }
                    continue
                df = pd.read_csv(path)
                namespace[ns_key] = df
                summary["csv"][stem] = _summarize_csv(df, size_kb)
            except Exception as exc:  # noqa: BLE001
                summary["csv"][stem] = {"loaded": False, "error": str(exc)[:200]}

    # JSON
    json_dir = context_root / "json"
    if json_dir.is_dir():
        for path in sorted(json_dir.glob("*.json")):
            stem = _safe_var_name(path.stem)
            ns_key = f"json_{stem}"
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = _json.load(f)
                namespace[ns_key] = data
                summary["json"][stem] = _summarize_json(data)
            except Exception as exc:  # noqa: BLE001
                summary["json"][stem] = {"loaded": False, "error": str(exc)[:200]}

    # SQLite
    db_dir = context_root / "db"
    if db_dir.is_dir():
        for path in sorted(db_dir.glob("*.db")):
            stem = _safe_var_name(path.stem)
            ns_key = f"conn_{stem}"
            try:
                conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
                conn.row_factory = sqlite3.Row
                namespace[ns_key] = conn
                summary["db"][stem] = _summarize_sqlite(conn)
            except Exception as exc:  # noqa: BLE001
                summary["db"][stem] = {"loaded": False, "error": str(exc)[:200]}

    # knowledge.md
    knowledge_path = context_root / "knowledge.md"
    if knowledge_path.is_file():
        try:
            knowledge["knowledge.md"] = knowledge_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            knowledge["knowledge.md"] = f"[read error: {exc}]"

    # doc/*.md  (and doc/*.sql since route plan called them necessary too)
    doc_dir = context_root / "doc"
    if doc_dir.is_dir():
        for ext in ("*.md", "*.sql"):
            for path in sorted(doc_dir.glob(ext)):
                key = f"doc/{path.name}"
                try:
                    knowledge[key] = path.read_text(encoding="utf-8", errors="replace")
                except Exception as exc:  # noqa: BLE001
                    knowledge[key] = f"[read error: {exc}]"

    return summary, knowledge


# ---------------------------------------------------------------------------
# Internal: per-type summarizers
# ---------------------------------------------------------------------------

def _summarize_csv(df: pd.DataFrame, size_kb: float) -> dict[str, Any]:
    cols: list[dict[str, Any]] = []
    n_rows = len(df)
    for col in df.columns:
        s = df[col]
        info: dict[str, Any] = {
            "name": str(col),
            "dtype": str(s.dtype),
        }
        try:
            null_pct = round(float(s.isna().mean()) * 100, 1) if n_rows else 0.0
            info["null_pct"] = null_pct
        except Exception:  # noqa: BLE001
            pass
        try:
            nunique = int(s.nunique(dropna=True))
            info["unique"] = nunique
        except Exception:  # noqa: BLE001
            nunique = 0

        # numeric stats
        if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
            try:
                info["min"] = _safe_scalar(s.min())
                info["max"] = _safe_scalar(s.max())
                info["mean"] = _safe_scalar(s.mean(), is_float=True)
            except Exception:  # noqa: BLE001
                pass
        # date stats
        elif pd.api.types.is_datetime64_any_dtype(s):
            try:
                info["min"] = str(s.min())
                info["max"] = str(s.max())
            except Exception:  # noqa: BLE001
                pass
        else:
            # categorical / text
            if 0 < nunique <= 20:
                try:
                    info["top"] = [str(v) for v in s.dropna().value_counts().head(5).index.tolist()]
                except Exception:  # noqa: BLE001
                    pass
            elif nunique > 0:
                try:
                    info["top"] = [str(v) for v in s.dropna().value_counts().head(3).index.tolist()]
                except Exception:  # noqa: BLE001
                    pass

        cols.append(info)

    return {
        "loaded": True,
        "rows": n_rows,
        "size_kb": int(size_kb),
        "columns": cols,
    }


def _summarize_json(data: Any, *, max_depth: int = 3) -> dict[str, Any]:
    info: dict[str, Any] = {"type": type(data).__name__}
    if isinstance(data, list):
        info["records"] = len(data)
        if data:
            info["sample"] = _truncate(_json.dumps(data[0], ensure_ascii=False, default=str), 300)
            if isinstance(data[0], dict):
                info["top_keys"] = list(data[0].keys())[:20]
    elif isinstance(data, dict):
        info["top_keys"] = list(data.keys())[:20]
        # If it looks like {"records": [...]}, surface that shape
        if "records" in data and isinstance(data["records"], list):
            info["records"] = len(data["records"])
            if data["records"]:
                info["sample"] = _truncate(
                    _json.dumps(data["records"][0], ensure_ascii=False, default=str), 300
                )
        else:
            info["sample"] = _truncate(_json.dumps(data, ensure_ascii=False, default=str), 300)
    else:
        info["sample"] = _truncate(repr(data), 200)
    return info


def _summarize_sqlite(conn: sqlite3.Connection) -> dict[str, Any]:
    cur = conn.cursor()
    cur.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    rows = cur.fetchall()
    tables: list[dict[str, Any]] = []
    for name, create_sql in rows:
        info: dict[str, Any] = {"name": name}
        try:
            cur.execute(f'SELECT COUNT(*) FROM "{name}"')
            info["rows"] = int(cur.fetchone()[0])
        except Exception as exc:  # noqa: BLE001
            info["rows"] = _UNKNOWN
            info["count_error"] = str(exc)[:120]
        info["create_sql"] = _truncate(str(create_sql or "").replace("\n", " "), 400)
        try:
            cur.execute(f'SELECT * FROM "{name}" LIMIT 3')
            sample_rows = [dict(r) for r in cur.fetchall()]
            info["sample"] = _truncate(_json.dumps(sample_rows, ensure_ascii=False, default=str), 400)
        except Exception:  # noqa: BLE001
            pass
        tables.append(info)
    return {"loaded": True, "tables": tables}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_var_name(stem: str) -> str:
    """转 stem -> 合法 Python 变量名."""
    out = []
    for ch in stem:
        out.append(ch if (ch.isalnum() or ch == "_") else "_")
    name = "".join(out)
    if not name or name[0].isdigit():
        name = "_" + name
    return name


def _safe_scalar(v: Any, *, is_float: bool = False) -> Any:
    try:
        if is_float:
            return round(float(v), 4)
        if hasattr(v, "item"):
            return v.item()
        return v
    except Exception:  # noqa: BLE001
        return _UNKNOWN


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 5] + "...'"
