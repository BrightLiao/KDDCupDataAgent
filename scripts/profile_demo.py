"""Profile the KDD Cup 2026 Phase 1 demo dataset.

Usage
-----
    uv run scripts/profile_demo.py
    uv run scripts/profile_demo.py --data-root data/demo/public --out reports/demo_profile.md

Produces a Markdown report covering:
    - total task count and ID range
    - difficulty distribution
    - context modality presence (csv / db / json / doc / knowledge.md)
    - per-task size distribution
    - gold.csv shape (rows, columns) and sample column names
    - doc/ length distribution (proxy for token scale)
    - knowledge.md length distribution

The script is read-only: it never writes into the dataset directory.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean, median


DIFFICULTIES = ("easy", "medium", "hard", "extreme")


@dataclass
class TaskRecord:
    task_id: str
    difficulty: str
    question: str
    input_dir: Path
    output_dir: Path
    context_kinds: tuple[str, ...]
    context_files: list[Path]
    gold_rows: int
    gold_cols: int
    gold_columns: list[str]
    input_bytes: int
    doc_bytes: int
    knowledge_chars: int


def human_bytes(n: int) -> str:
    for unit in ("B", "K", "M", "G"):
        if n < 1024:
            return f"{n:.0f}{unit}"
        n /= 1024
    return f"{n:.0f}T"


def dir_size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def detect_context_kinds(ctx_dir: Path) -> tuple[str, ...]:
    kinds = []
    for sub in ("csv", "db", "json", "doc"):
        if (ctx_dir / sub).is_dir():
            kinds.append(sub)
    if (ctx_dir / "knowledge.md").is_file():
        kinds.append("knowledge.md")
    return tuple(kinds)


def read_gold(path: Path) -> tuple[int, int, list[str]]:
    if not path.is_file():
        return 0, 0, []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return 0, 0, []
        rows = sum(1 for _ in reader)
    return rows, len(header), header


def load_tasks(public_root: Path) -> list[TaskRecord]:
    input_root = public_root / "input"
    output_root = public_root / "output"
    if not input_root.is_dir() or not output_root.is_dir():
        raise SystemExit(f"Expected {input_root} and {output_root} to exist.")

    tasks: list[TaskRecord] = []
    for td in sorted(input_root.glob("task_*"), key=lambda p: int(p.name.split("_")[1])):
        task_json = td / "task.json"
        if not task_json.is_file():
            continue
        meta = json.loads(task_json.read_text(encoding="utf-8"))
        ctx_dir = td / "context"
        kinds = detect_context_kinds(ctx_dir) if ctx_dir.is_dir() else ()
        files = sorted(p for p in ctx_dir.rglob("*") if p.is_file()) if ctx_dir.is_dir() else []
        doc_bytes = dir_size(ctx_dir / "doc") if (ctx_dir / "doc").is_dir() else 0
        know = ctx_dir / "knowledge.md"
        kchars = len(know.read_text(encoding="utf-8")) if know.is_file() else 0

        out_dir = output_root / td.name
        gold_rows, gold_cols, gold_cols_list = read_gold(out_dir / "gold.csv")

        tasks.append(
            TaskRecord(
                task_id=meta["task_id"],
                difficulty=meta["difficulty"],
                question=meta["question"],
                input_dir=td,
                output_dir=out_dir,
                context_kinds=kinds,
                context_files=files,
                gold_rows=gold_rows,
                gold_cols=gold_cols,
                gold_columns=gold_cols_list,
                input_bytes=dir_size(td),
                doc_bytes=doc_bytes,
                knowledge_chars=kchars,
            )
        )
    return tasks


def summarize(tasks: list[TaskRecord]) -> str:
    out: list[str] = []
    out.append("# Phase 1 Demo Profile")
    out.append("")
    out.append(f"- Total tasks: **{len(tasks)}**")
    ids_int = sorted(int(t.task_id.split("_")[1]) for t in tasks)
    out.append(f"- Task ID range: `task_{ids_int[0]}` .. `task_{ids_int[-1]}` (non-contiguous)")
    out.append(f"- Total input bytes: {human_bytes(sum(t.input_bytes for t in tasks))}")
    out.append("")

    # Difficulty distribution
    diff_counter = Counter(t.difficulty for t in tasks)
    out.append("## Difficulty distribution")
    out.append("")
    out.append("| Difficulty | Count |")
    out.append("| --- | --- |")
    for d in DIFFICULTIES:
        out.append(f"| {d} | {diff_counter.get(d, 0)} |")
    out.append("")

    # Context kind presence
    out.append("## Context modality presence (by difficulty)")
    out.append("")
    out.append("| Difficulty | csv | db | json | doc | knowledge.md | n |")
    out.append("| --- | --- | --- | --- | --- | --- | --- |")
    for d in DIFFICULTIES:
        bucket = [t for t in tasks if t.difficulty == d]
        if not bucket:
            continue
        counts = {k: sum(1 for t in bucket if k in t.context_kinds) for k in ("csv", "db", "json", "doc", "knowledge.md")}
        out.append(
            f"| {d} | {counts['csv']} | {counts['db']} | {counts['json']} | {counts['doc']} | {counts['knowledge.md']} | {len(bucket)} |"
        )
    out.append("")

    # Size distribution per difficulty
    out.append("## Input size per difficulty (MB)")
    out.append("")
    out.append("| Difficulty | min | median | mean | max |")
    out.append("| --- | --- | --- | --- | --- |")
    for d in DIFFICULTIES:
        bucket = [t.input_bytes / 1024 / 1024 for t in tasks if t.difficulty == d]
        if not bucket:
            continue
        out.append(f"| {d} | {min(bucket):.1f} | {median(bucket):.1f} | {mean(bucket):.1f} | {max(bucket):.1f} |")
    out.append("")

    # Doc byte distribution
    out.append("## doc/ size among hard/extreme tasks")
    out.append("")
    out.append("| task_id | difficulty | doc/ size |")
    out.append("| --- | --- | --- |")
    for t in sorted([t for t in tasks if t.doc_bytes > 0], key=lambda x: x.doc_bytes):
        out.append(f"| {t.task_id} | {t.difficulty} | {human_bytes(t.doc_bytes)} |")
    out.append("")

    # Gold.csv shape
    out.append("## gold.csv shape")
    out.append("")
    out.append("| task_id | difficulty | rows | cols | columns |")
    out.append("| --- | --- | --- | --- | --- |")
    for t in tasks[:10]:
        col_preview = ", ".join(f"`{c}`" for c in t.gold_columns)
        out.append(f"| {t.task_id} | {t.difficulty} | {t.gold_rows} | {t.gold_cols} | {col_preview} |")
    out.append("")
    rows = [t.gold_rows for t in tasks]
    cols = [t.gold_cols for t in tasks]
    out.append(f"- gold rows: min={min(rows)} median={median(rows):.0f} max={max(rows)}")
    out.append(f"- gold cols: min={min(cols)} median={median(cols):.0f} max={max(cols)}")
    out.append("")

    # SQL-alias detection in column names
    import re

    sql_alias_pat = re.compile(r"(COUNT|SUM|AVG|MIN|MAX|CAST|DISTINCT|CASE)", re.IGNORECASE)
    sql_alias_hits = sum(1 for t in tasks for c in t.gold_columns if sql_alias_pat.search(c))
    total_cols = sum(len(t.gold_columns) for t in tasks)
    out.append(f"- columns containing SQL keywords (COUNT/SUM/CAST/...): **{sql_alias_hits} / {total_cols}**")
    out.append("  → evidence that demo is reformatted from BIRD-like benchmarks.")
    out.append("")

    # knowledge.md stats
    kchars = [t.knowledge_chars for t in tasks if t.knowledge_chars > 0]
    if kchars:
        out.append(
            f"- knowledge.md present in {len(kchars)}/{len(tasks)} tasks, "
            f"chars min={min(kchars)} median={int(median(kchars))} max={max(kchars)}"
        )
        out.append("")

    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", type=Path, default=Path("data/demo/public"))
    ap.add_argument("--out", type=Path, default=None, help="optional Markdown report path")
    args = ap.parse_args()

    tasks = load_tasks(args.data_root)
    report = summarize(tasks)
    print(report)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print(f"\n[written to {args.out}]")


if __name__ == "__main__":
    main()
