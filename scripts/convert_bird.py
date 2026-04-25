"""Convert BIRD (arXiv:2305.03111) samples into KDD Cup 2026 task format.

BIRD's dev set (~1,534 samples, ~11 databases) is the closest public proxy for
the KDD Cup demo distribution (§附录 B of docs/方案调研综述.md). This script
ingests BIRD's native layout and emits directories shaped like
``data/public/input/task_<id>`` + ``data/public/output/task_<id>/gold.csv``.

BIRD download
-------------
    https://bird-bench.github.io/
    - dev.zip  (≈ 1.5 GB):  dev_databases/<db_id>/*.sqlite + dev.json
    - dev.json entry:
        {
          "question_id": int,
          "db_id": str,
          "question": str,
          "evidence": str,        # external knowledge, maps to knowledge.md
          "SQL": str,             # gold SQL, executed against SQLite to get gold.csv
          "difficulty": "simple" | "moderate" | "challenging"
        }

Usage
-----
    uv run scripts/convert_bird.py \
        --bird-root /path/to/bird/dev \
        --out data/external/bird_heldout \
        --sample 200 \
        --seed 42

    uv run scripts/convert_bird.py --dry-run --bird-root /path/to/bird/dev

After conversion, use ``scripts/profile_demo.py --data-root
data/external/bird_heldout`` to verify the converted corpus has shape similar
to the official demo.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import shutil
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterator


# BIRD difficulty labels -> KDD Cup difficulty buckets.
# KDD Cup's difficulty is by *modality complexity*, not SQL complexity.
# Since BIRD entries carry a SQLite DB + evidence text (no long doc/), they
# map most naturally to "medium" — with harder BIRD SQL still staying medium
# in KDD Cup terms. Hard/extreme require doc/ which BIRD does not provide.
BIRD_TO_KDD = {
    "simple": "medium",
    "moderate": "medium",
    "challenging": "medium",
}


def read_bird_entries(bird_root: Path) -> tuple[list[dict], Path]:
    """Load BIRD's dev.json. Returns (entries, databases_dir)."""
    # BIRD's dev pack is usually laid out as:
    #   bird_root/dev.json   (or dev_20240627/dev.json)
    #   bird_root/dev_databases/<db_id>/<db_id>.sqlite
    candidates_json = [
        bird_root / "dev.json",
        bird_root / "dev_20240627" / "dev.json",
        bird_root / "dev_20230627" / "dev.json",
    ]
    dev_json = next((p for p in candidates_json if p.is_file()), None)
    if dev_json is None:
        raise SystemExit(f"Could not find dev.json under {bird_root}. Expected one of: {candidates_json}")

    candidates_dbs = [
        bird_root / "dev_databases",
        bird_root / "dev_20240627" / "dev_databases",
        bird_root / "dev_20230627" / "dev_databases",
        dev_json.parent / "dev_databases",
    ]
    db_dir = next((p for p in candidates_dbs if p.is_dir()), None)
    if db_dir is None:
        raise SystemExit(f"Could not find dev_databases/ near {dev_json}. Expected one of: {candidates_dbs}")

    entries = json.loads(dev_json.read_text(encoding="utf-8"))
    return entries, db_dir


def pick_sample(
    entries: list[dict],
    n: int,
    per_difficulty: bool,
    seed: int,
) -> list[dict]:
    """Sample ``n`` entries. If per_difficulty, sample roughly 1/3 from each bucket."""
    rng = random.Random(seed)
    if not per_difficulty:
        return rng.sample(entries, min(n, len(entries)))

    by_diff: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        by_diff[e.get("difficulty", "moderate")].append(e)

    buckets = list(by_diff.keys())
    quota = {b: n // len(buckets) for b in buckets}
    # give remainder to the "challenging" bucket if present, else first
    remainder = n - sum(quota.values())
    fill_order = ["challenging", "moderate", "simple"]
    for b in fill_order:
        if remainder <= 0:
            break
        if b in quota:
            quota[b] += 1
            remainder -= 1

    out: list[dict] = []
    for b, k in quota.items():
        pool = by_diff[b]
        rng.shuffle(pool)
        out.extend(pool[:k])
    rng.shuffle(out)
    return out


def run_sql_to_csv(db_path: Path, sql: str, out_csv: Path) -> tuple[int, int]:
    """Execute SQL against SQLite, write result as CSV. Returns (rows, cols)."""
    if not db_path.is_file():
        raise FileNotFoundError(db_path)
    con = sqlite3.connect(db_path)
    con.text_factory = str
    try:
        cur = con.cursor()
        cur.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchall()
    finally:
        con.close()

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow(r)
    return len(rows), len(cols)


SCHEMA_SQL = """
SELECT m.name AS table_name, p.name AS column_name, p.type AS column_type
FROM sqlite_master m
JOIN pragma_table_info(m.name) p
WHERE m.type='table' AND m.name NOT LIKE 'sqlite_%'
ORDER BY m.name, p.cid
"""


def build_knowledge_md(db_path: Path, evidence: str | None, db_id: str) -> str:
    """Build a knowledge.md placeholder from schema + BIRD evidence."""
    con = sqlite3.connect(db_path)
    try:
        schema = con.execute(SCHEMA_SQL).fetchall()
    finally:
        con.close()

    lines = [f"# Knowledge Guide for `{db_id}` database", ""]
    lines.append("## Schema")
    lines.append("")
    current_table = None
    for tname, col, ctype in schema:
        if tname != current_table:
            lines.append(f"### `{tname}`")
            current_table = tname
        lines.append(f"- **{col}** ({ctype})")
    lines.append("")

    if evidence:
        lines.append("## Business Knowledge (from BIRD `evidence`)")
        lines.append("")
        lines.append(evidence)
        lines.append("")

    return "\n".join(lines)


def new_task_id(question_id: int) -> str:
    return f"task_b{question_id:04d}"


def convert_one(
    entry: dict,
    db_dir_bird: Path,
    out_input_root: Path,
    out_output_root: Path,
) -> tuple[bool, str]:
    """Convert one BIRD entry. Returns (ok, reason)."""
    qid = entry["question_id"]
    db_id = entry["db_id"]
    question = entry["question"]
    sql = entry["SQL"]
    bird_diff = entry.get("difficulty", "moderate")
    evidence = entry.get("evidence", "")

    task_id = new_task_id(qid)
    kdd_diff = BIRD_TO_KDD.get(bird_diff, "medium")

    bird_db = db_dir_bird / db_id / f"{db_id}.sqlite"
    if not bird_db.is_file():
        return False, f"missing db file: {bird_db}"

    in_dir = out_input_root / task_id
    out_dir = out_output_root / task_id
    (in_dir / "context" / "db").mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    # task.json
    (in_dir / "task.json").write_text(
        json.dumps(
            {"task_id": task_id, "difficulty": kdd_diff, "question": question},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    # db
    shutil.copy(bird_db, in_dir / "context" / "db" / f"{db_id}.db")
    # knowledge.md
    (in_dir / "context" / "knowledge.md").write_text(
        build_knowledge_md(bird_db, evidence, db_id),
        encoding="utf-8",
    )
    # gold.csv
    try:
        rows, cols = run_sql_to_csv(bird_db, sql, out_dir / "gold.csv")
    except Exception as e:
        return False, f"SQL exec failed: {e}"

    # metadata sidecar (for later debugging; not part of the official format,
    # kept outside task.json so agents cannot rely on it)
    (out_dir / "_bird_meta.json").write_text(
        json.dumps(
            {
                "bird_question_id": qid,
                "bird_db_id": db_id,
                "bird_difficulty": bird_diff,
                "gold_sql": sql,
                "gold_rows": rows,
                "gold_cols": cols,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return True, f"rows={rows} cols={cols}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bird-root", type=Path, required=False, default=Path("data/external/bird/dev"))
    ap.add_argument("--out", type=Path, default=Path("data/external/bird_heldout"))
    ap.add_argument("--sample", type=int, default=100, help="how many tasks to convert (0 = all)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--balanced", action="store_true", default=True, help="sample balanced across BIRD difficulty")
    ap.add_argument("--dry-run", action="store_true", help="list what would be converted without writing")
    args = ap.parse_args()

    if not args.bird_root.exists():
        print(
            f"[skip] BIRD data not found at {args.bird_root}.\n"
            "Download BIRD from https://bird-bench.github.io/ and unpack so the layout matches:\n"
            f"  {args.bird_root}/dev.json\n"
            f"  {args.bird_root}/dev_databases/<db_id>/<db_id>.sqlite\n",
            file=sys.stderr,
        )
        sys.exit(2)

    entries, db_dir_bird = read_bird_entries(args.bird_root)
    print(f"[bird] loaded {len(entries)} entries, db dir={db_dir_bird}")
    diff_hist = Counter(e.get("difficulty", "moderate") for e in entries)
    print(f"[bird] difficulty distribution: {dict(diff_hist)}")

    target_n = args.sample if args.sample > 0 else len(entries)
    picks = pick_sample(entries, target_n, per_difficulty=args.balanced, seed=args.seed)
    print(f"[bird] sampled {len(picks)} entries (balanced={args.balanced}, seed={args.seed})")

    if args.dry_run:
        for e in picks[:10]:
            print(f"  would convert q{e['question_id']:05d}  db={e['db_id']:<25s}  diff={e.get('difficulty')}")
        print(f"  ... ({len(picks)} total)")
        return

    in_root = args.out / "input"
    out_root = args.out / "output"
    in_root.mkdir(parents=True, exist_ok=True)
    out_root.mkdir(parents=True, exist_ok=True)

    ok = 0
    fail = 0
    for e in picks:
        success, msg = convert_one(e, db_dir_bird, in_root, out_root)
        if success:
            ok += 1
        else:
            fail += 1
            print(f"  [fail] q{e['question_id']:05d} {e['db_id']}: {msg}", file=sys.stderr)

    print(f"\n[done] converted {ok}/{len(picks)} (failures: {fail})")
    print(f"  input:  {in_root}")
    print(f"  output: {out_root}")


if __name__ == "__main__":
    main()
