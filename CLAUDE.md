# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository purpose

KDD Cup 2026 Track: Data Agents — agent reads a natural-language data-science question + multimodal assets (CSV / SQLite / JSON / docs), explores autonomously, and writes a `prediction.csv`. Scoring is column multiset based: `Score = Recall − 0.5 · (Extra Cols / Predicted Cols)` (column names and row order ignored). Backend LLM is Qwen3.5-35B-A3B via Aliyun Bailian's OpenAI-compatible API.

## Multi-package layout (critical context)

Four Python packages coexist at the repo root, wired together with **uv path-deps** (editable). The dependency chain matters when running, building, or packaging:

```
kddcup2026-starter-kit/   →  data-agent-baseline   (official ReAct + tools, the upstream baseline)
data_agent_v0/            →  data-agent-v0         (depends on baseline; defines shape/repl/executor/planner reused by v1)
data_agent_baseline_v1/   →  data-agent-baseline-v1 (depends on BOTH baseline AND v0 — first submission agent)
tools/agent_diagnose/     →  agent-diagnose        (depends on baseline + v0 for prompt reconstruction)
```

Layered architecture (each layer adds a single change vs. the previous):

- **baseline** — official ReAct with JSON actions
- **L1 CodeAct** — replace JSON action with ` ```python ` code blocks (kills three-quote escape loops)
- **L2 schema preload** — head + dtypes + `knowledge.md` injected into prompt at startup
- **L3 shape spec** — one extra LLM call to parse `expected_columns` / `expected_row_count` from the question for column alignment before submit
- **L4 plan-executor + difficulty routing** — only in `data_agent_v0`; planner emits a short plan, executor branches by easy/medium/hard/extreme

`data_agent_baseline_v1` = baseline + L1 + L2 + L3 (no planner). `data_agent_v0` = baseline_v1 + L4 (plan-executor + shape/plan 合一 + knowledge 完整注入). Current best: **agent_v0_tuned** (micro 0.627, +0.04 vs baseline_v1's 0.585). See `docs/VERSION_HISTORY.md` for full evolution — this CLAUDE.md section is a snapshot; version history is ground truth.

Each agent's `Orchestrator.run(task)` returns `(AgentRunResult, _OrchestratorTrace)` and reuses starter-kit's runner; v1 deliberately keeps `routed_branch="flat"` and empty plan/replan_events so the diagnose UI doesn't need a code path per agent.

## Common commands

All Python work goes through **uv** in each package directory (separate venvs per package by design — keeps deps from conflicting):

```bash
# First-time setup, per package
cd kddcup2026-starter-kit && uv sync
cd ../data_agent_v0       && uv sync
cd ../data_agent_baseline_v1 && uv sync
cd ../tools/agent_diagnose && uv sync

# Run agents (CLI entrypoints declared in each pyproject.toml)
cd kddcup2026-starter-kit && ./run_baseline.sh run-benchmark      # baseline
cd data_agent_baseline_v1 && ./run_baseline_v1.sh run-benchmark   # baseline_v1
cd data_agent_v0          && ./run_v0.sh run-benchmark            # v0

# The run_*.sh wrappers read BAILIAN_API_KEY from ../.env and substitute the
# placeholder in configs/<agent>.local.yaml → configs/<agent>.runtime.yaml,
# then run `uv run agent-baseline-v1 / agentv0` etc. Never edit the *.runtime.yaml
# (it's regenerated each run); edit *.local.yaml instead. Both *.runtime.yaml and
# *.local.yaml are gitignored — the example config to commit is *.example.yaml.
```

```bash
# Single-task run (instead of full benchmark)
./run_v0.sh run-task task_11

# Subset / smoke
./run_baseline_v1.sh run-benchmark --limit 5
```

```bash
# Tests (pytest, configured per package)
cd data_agent_baseline_v1 && uv run pytest
cd data_agent_v0          && uv run pytest
cd tools/agent_diagnose   && uv run pytest

# Single test
uv run pytest tests/test_orchestrator.py::test_flat_run -xvs

# Lint (ruff, line-length=100, py310)
uv run ruff check src tests
```

```bash
# Eval — single run scoring (run from repo root)
uv run python -m src.eval.enhanced_eval \
    --runs <pkg>/artifacts/runs/<run_id> \
    --gold-root data/demo/public/output \
    --input-root data/demo/public/input \
    --version-id <label> \
    --out reports/<label>_eval_report.json

# 3-seed wrapper (drives the agent 3× with seeds no_seed/42/43, aggregates, optional diff)
bash scripts/run_3seed_eval.sh \
    --agent-dir data_agent_baseline_v1 \
    --run-script ./run_baseline_v1.sh \
    --config configs/baseline_v1.local.yaml \
    --run-id-base demo_qwen35_baseline_v1 \
    --version-id baseline_v1_3seed \
    --seeds no_seed,42,43 \
    --diff-base baseline_3seed
# Supports --skip-done (resume) and --limit N (subset smoke).
```

```bash
# Diagnose web UI
cd tools/agent_diagnose
./run_diagnose.sh           # local 127.0.0.1:8000 with --reload
./serve_remote.sh 8000      # nohup 0.0.0.0:8000, pid → .diagnose.pid
```

## Docker submission packaging

Two agents can be packaged: `data_agent_baseline_v1` (legacy) and `data_agent_v0` (current, micro 0.627). Both Dockerfiles live in their directories, but **build context must be the repo root** — images need all sibling packages at the same relative paths so `uv sync --frozen --no-dev` resolves path-deps.

**Current recommended: `data_agent_v0/Dockerfile`** (agent_v0_tuned, v2).

```bash
# Build (from repo root)
docker buildx build --platform linux/amd64 --load \
  -f data_agent_v0/Dockerfile -t kddcup-v0:latest .

# Smoke test (5 tasks) — set up INPUT/OUTPUT/LOGS dirs, copy 5 demo tasks, then:
docker run --rm --cpus=16 --memory=64g \
  -v "$INPUT:/input:ro" -v "$OUTPUT:/output:rw" -v "$LOGS:/logs:rw" \
  -e MODEL_API_URL="$BAILIAN_URL" -e MODEL_API_KEY="$API_KEY" -e MODEL_NAME="qwen-plus" \
  kddcup-v0:latest

# Full 50-task test: copy all 50 demo tasks, same run command.
# Expected ~32min wall time → ~4.3h projected for 400 tasks (under 12h cap).
```

Legacy: `bash data_agent_baseline_v1/submit_pipeline.sh`

| Stage | Script | Checks |
| --- | --- | --- |
| 1 build | `build_and_test_docker.sh` | buildx amd64 → 5-task online smoke → `--network=none` must write error CSV → secret-string scan over `/build/.../src` → tar.gz ≤10GB |
| 2 archive verify | `verify_archive.sh` | docker load → 3 packages present → `max_retries=0` baked in → `/build` read-only → PID 1=tini → single-task `--network=none` writes error CSV |
| 3 submission verify | `verify_submission.sh` | full 50 tasks online → `enhanced_eval` → diff vs. baseline_v1 3-seed (±0.05 micro tolerance) → wallclock × 8 < 11h projection |

Packaging invariants (see `docs/DOCKER_PACKAGING.md` for the "5 red lines"):

- **PID 1 = tini** — required to reap CodeAct REPL multiprocessing.spawn workers
- **`max_retries=0`** baked into `EnvModelAdapter` — without it, `--network=none` hangs in OpenAI client retry loop
- **SIGALRM wallclock timeout** is wrapped only in `submit_runner.py` main process; the REPL spawn worker is intentionally NOT wrapped
- **Dynamic per-task budget** in `entrypoint.py`: `max(900s, remaining_time / remaining_tasks)`, easy tasks ordered first, leaves 30 min buffer under the 12h cap
- **Aliyun PyPI mirror + BuildKit cache mount** in Dockerfile so on Ali4KDD the build context stays ~988 KB and wheels are reused across builds

## Eval & scoring

- `src/eval/scorer.py` is the column-multiset scorer (matches the official spec; case-insensitive, dedup on the prediction side, λ=0.5)
- `src/eval/enhanced_eval.py` aggregates 5 metric families across multiple runs: `accuracy` (micro/macro), `distribution` (difficulty × data type), `submission` (rate, n_perfect/n_zero), `failure_clusters` (timeout / parse_error / api_error / no_submit / other), `consistency` (cross-seed all_agree / majority_agree / answer_entropy)
- The protocol is **3 seed × 50 task** — single-seed numbers are unreliable. See `docs/EVAL_PLAN_30D.md`.
- Per-task artifacts live at `<pkg>/artifacts/runs/<run_id>/task_<id>/{trace.json, prediction.csv}`; aggregated reports at `reports/<run_id>_scored.json` and `reports/<version>_eval_report.json`.

## Diagnose tool conventions

`tools/agent_diagnose` reads only `<pkg>/artifacts/runs/<run_id>/task_*/{trace.json, prediction.csv}` + `reports/<run_id>_scored.json`. It does not modify any agent code; the LLM-input column is **reconstructed at the diagnose layer** by importing baseline / v0 prompt builders — agent-side has zero instrumentation. Marked "ⓘ reconstructed" in the UI.

Agent-kind naming (`AGENT_KIND_ORDER` in `tools/agent_diagnose/src/agent_diagnose/config.py`) — adding a new entry there is the single source of truth that lights up tables / cards / matrices / color families:

- `baseline` — original (ReAct + JSON action)
- `baseline_v*` — patches on top of baseline (CodeAct + hyperparams; e.g. `baseline_v1`)
- `agent_v*` — architectural rewrites (e.g. `agent_v0` = first rewrite; future `agent_v1`, `agent_v2`, …)

Only fully-completed 50-task runs show up on `/overview`; half-finished runs are auto-hidden.

## Version control & collaboration conventions

This repo is developed by 4 people, all using Claude Code. Follow these conventions so multiple CC instances stay coherent:

**Branching — GitHub Flow, no GitFlow.**
- `main` is always submittable; competition submissions are tags on `main`.
- Each task on a short-lived `feat/<name>-<short-desc>` branch, PR back to `main`.
- One person owns each agent version at a time — do NOT edit another agent's `data_agent_v*/` or `data_agent_baseline_v*/` without coordinating. If unsure who owns it, ask before editing.
- Cross-cutting work (`tools/agent_diagnose/`, `src/eval/`, `scripts/`, `docs/`) is shared but lower-conflict — still prefer a feature branch + PR.

**New agent version = new directory, never in-place rewrite.**
- New `agent_v*` (architectural rewrite): `cp -r data_agent_v0 data_agent_v1`, then add a line to `AGENT_KIND_ORDER` in `tools/agent_diagnose/src/agent_diagnose/config.py` (single source of truth — diagnose tables/cards/matrices auto-pick it up).
- New `baseline_v*` (patch on top of baseline): same pattern from `data_agent_baseline_v1`.
- Old versions stay untouched so 3-seed regression comparisons keep working. Disk is cheap; lost regression baselines are not.

**Release anchors — git tag every 3-seed-validated version.**
- Tag format: `<agent_kind>-3seed-YYYYMMDD` (e.g. `baseline_v1-3seed-20260427`).
- When packaging a Docker submission, append a row to `submission_log.md` with: tag, commit hash, image tar.gz name, 3-seed micro/macro/sub-rate. This is how you reverse-look-up "which code produced this score."

**Per-developer identity (how CC knows who is running it).**
All four teammates develop on the **same shared Linux server** (often as the same OS user, e.g. `root`). This means a single `CLAUDE.local.md` cannot disambiguate users, and `git config user.name` is also globally shared. The only reliable identity signal is **the human telling CC who they are at session start**.

Convention:

- Each teammate keeps their own `CLAUDE.local.<short-name>.md` at the repo root, e.g. `CLAUDE.local.brightliao.md`, `CLAUDE.local.shenhao.md`. All such files match the gitignore pattern `CLAUDE.local.*.md` (the committed template `CLAUDE.local.md.example` is whitelisted). Per-teammate files only carry **identity + pointers + CC preferences**, never the task list itself.
- **Current task assignments and hands-off scope live in [`docs/PHASE_PLAN.md`](docs/PHASE_PLAN.md), single source of truth.** The Current Phase section at the top has the "团队成员与分工" and "Task 清单" tables. Phase switches update only that file — per-user `CLAUDE.local.<name>.md` files do not need editing.
- The lead developer is `brightliao` (廖老师); other teammates currently have role `learning`. Ownership of `data_agent_*/` directories is fluid; PHASE_PLAN.md says who owns what this phase.
- CC sessions are per-process, so identity must be re-established each session — there is no persistent OS-level signal to rely on.

**Required behavior on session start (CC must do this BEFORE non-trivial edits):**

1. Ask the user up front: *"Which teammate is this session — brightliao, shenhao, wangchenzhang, wangyumeng, or someone else? (Used to load the right `CLAUDE.local.<name>.md`.)"* Run `ls CLAUDE.local.*.md` to see who has files set up.
2. **If a `CLAUDE.local.<name>.md` matches the answer:** read it; then read [`docs/PHASE_PLAN.md`](docs/PHASE_PLAN.md) — the Current Phase section's "团队成员与分工" and "Task 清单" tables tell you what this teammate owns this phase. Respect those declarations for the rest of the session.
3. **If no matching file exists** (new teammate, or first time on this checkout): run a short identity intake before any edits — ask name, role (`lead` | `contributor` | `learning`), CC preferences. Then point them at `docs/PHASE_PLAN.md` to confirm/agree their Current Phase task assignment. Write `CLAUDE.local.<name>.md` from `CLAUDE.local.md.example` (identity + pointers only — do not duplicate task content), confirm, then proceed.
4. If the user's request would touch a `data_agent_*/` or other directory outside their PHASE_PLAN.md task scope, surface that and confirm before editing — that area may be owned by another teammate this phase.
5. Caveat: `git config user.name` is unreliable on the shared account; use it as supporting signal only, not as authoritative identity.
6. The harness's auto-memory dir (`~/.claude/projects/.../memory/`) is also shared across teammates on this account — when writing a memory, prefix entries with the active teammate's short-name (e.g. `[brightliao] ...`) so cross-session reads stay attributable. Avoid writing personal preferences as if they were team-wide.

For real-time "who edited what recently," CC can also check `git log --oneline -20 -- <dir>` and `git branch -a --sort=-committerdate | head`; if a target dir has commits from someone other than the current teammate in the last few days, surface that before editing.

**Other rules for Claude Code instances editing this repo:**
- Never edit `*.runtime.yaml` (regenerated each run) or commit `*.local.yaml` (gitignored, has secrets).
- When asked to "run a 3-seed eval," produce a tag + a `submission_log.md` row as part of completion — not just the report JSON.
- Do not delete or refactor files in older agent dirs (`kddcup2026-starter-kit`, `data_agent_v0`, etc.) for "cleanup" — they are load-bearing for regression comparison.
- For teammates marked `learning` in `CLAUDE.local.md`: be more conservative — narrate plan before non-trivial edits, prefer small PRs, and confirm before touching anything outside their stated focus.

## Things that will trip you up

- `data_agent_v0/data` and `data_agent_baseline_v1/data` are **gitignored symlinks** to `../data`; don't commit them.
- `*.local.yaml` and `*.runtime.yaml` are gitignored secrets-bearing configs — only `*.example.yaml` is checked in.
- `uv.lock` IS committed (required for reproducible Docker builds) — do not gitignore it.
- The repo root has separate `pyproject.toml`-less Python at `src/eval/` (run with `uv run python -m src.eval.enhanced_eval` from any of the agent dirs that have uv envs, or from repo root with one of the package envs activated).
- Documentation is mostly in **Chinese** under `docs/` — `docs/VERSION_HISTORY.md` tracks per-version goals/changes/3-seed validation, `docs/DOCKER_PACKAGING.md` is the packaging gotcha list.
