"""FastAPI app —— P1 概览 + P2 单题回放（待实现）。"""
from __future__ import annotations

import argparse
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from agent_diagnose.config import REPO_ROOT  # noqa: F401  also sets sys.path
from agent_diagnose.data import (
    discover_eval_reports,
    discover_runs,
    get_run,
    list_all_task_ids,
    load_eval_report,
    load_gold_csv,
    load_prediction_csv,
    load_task_input,
    load_trace,
)
from agent_diagnose.diff import diff_csv
from agent_diagnose.markdown_helper import md_to_html
from agent_diagnose.normalize import detect_agent_kind, extract_planner_calls, normalize_steps
from agent_diagnose.scoring import score_run_lazy
from agent_diagnose.stats import (
    RunKPIs,
    agent_kind_color_class,
    aggregate_by_agent_kind,
    compute_run_kpis,
    filter_task_ids_by_kind,
    kind_score_matrix,
    pick_reference_and_challenger_kinds,
    score_cell_class,
    sort_kpis_by_kind,
    task_difficulty_map,
    task_score_matrix,
)

PKG_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = PKG_DIR / "templates"
STATIC_DIR = PKG_DIR / "static"

app = FastAPI(title="Agent Diagnose", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["score_cell_class"] = score_cell_class
templates.env.globals["agent_kind_color_class"] = agent_kind_color_class


@app.get("/healthz", response_class=HTMLResponse)
def healthz() -> str:
    return "ok"


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/overview", status_code=302)


# ---------------------------------------------------------------------------
# P1 Overview
# ---------------------------------------------------------------------------

def _build_overview_context(filter_mode: str) -> dict:
    runs = discover_runs()
    all_task_ids = list_all_task_ids()
    expected_n = len(all_task_ids) or 50  # 完整 run 的题数（demo = 50）

    raw_kpis: list[RunKPIs] = []
    for run in runs:
        k = compute_run_kpis(run)
        if k is not None:
            raw_kpis.append(k)
    # 仅保留完整跑完 expected_n 题的 run，其余隐藏（不列、不参与均值）
    kpis_list = [k for k in raw_kpis if k.n_tasks == expected_n]
    n_incomplete = len(raw_kpis) - len(kpis_list)

    kpis_list = sort_kpis_by_kind(kpis_list)
    agg_list = aggregate_by_agent_kind(kpis_list)
    difficulty_map = task_difficulty_map(kpis_list)
    kind_matrix = kind_score_matrix(kpis_list)
    ref_kind, chg_kind = pick_reference_and_challenger_kinds(agg_list)
    filtered = filter_task_ids_by_kind(all_task_ids, kind_matrix, ref_kind, chg_kind, filter_mode)
    kinds_for_columns = [a.agent_kind for a in agg_list]
    return {
        "runs": runs,
        "kpis_list": kpis_list,
        "agg_list": agg_list,
        "kind_matrix": kind_matrix,
        "difficulty_map": difficulty_map,
        "reference_kind": ref_kind,
        "challenger_kind": chg_kind,
        "all_task_ids": all_task_ids,
        "filtered_task_ids": filtered,
        "filter_mode": filter_mode,
        "kinds_for_columns": kinds_for_columns,
        "expected_n": expected_n,
        "n_incomplete": n_incomplete,
    }


@app.get("/overview", response_class=HTMLResponse)
def overview(request: Request, filter: str = "all"):
    ctx = _build_overview_context(filter)
    return templates.TemplateResponse(
        request,
        "overview.html",
        {"active_page": "overview", "active_task_id": None, "active_run_id": None, **ctx},
    )


@app.get("/api/score_matrix", response_class=HTMLResponse)
def api_score_matrix(request: Request, filter: str = "all"):
    ctx = _build_overview_context(filter)
    return templates.TemplateResponse(request, "partials/score_matrix.html", ctx)


# ---------------------------------------------------------------------------
# P2 Task Replay
# ---------------------------------------------------------------------------

@app.get("/task/{task_id}", response_class=HTMLResponse)
def task_replay(request: Request, task_id: str, run: str = ""):
    all_runs = discover_runs()
    if not all_runs:
        return HTMLResponse(f"<p>No runs found. Run baseline or v0 first.</p>", status_code=404)

    selected_run = None
    if run:
        selected_run = get_run(run)
    if selected_run is None:
        # default: pick first run that actually has this task
        for r in all_runs:
            if (r.runs_dir / task_id / "trace.json").is_file():
                selected_run = r
                break
    if selected_run is None:
        selected_run = all_runs[0]

    trace = load_trace(selected_run.run_id, task_id)
    if trace is None:
        return HTMLResponse(
            f"<p>No trace.json for {task_id} in run {selected_run.run_id}</p>",
            status_code=404,
        )

    agent_kind = selected_run.agent_kind or detect_agent_kind(trace)
    v0_meta = trace.get("v0_meta")

    task_input = load_task_input(task_id)
    knowledge_md = task_input.get("knowledge_md")
    knowledge_html = md_to_html(knowledge_md) if knowledge_md else None

    steps = normalize_steps(trace, agent_kind, task_input=task_input)
    planner_calls = extract_planner_calls(trace, task_input)

    pred = load_prediction_csv(selected_run.run_id, task_id)
    gold = load_gold_csv(task_id)
    diff = diff_csv(pred, gold)

    # locate per-task score from this run's scored.json
    scored = score_run_lazy(selected_run)
    score_info = None
    difficulty = ""
    if scored:
        for t in scored.get("tasks", []):
            if t.get("task_id") == task_id:
                score_info = t
                difficulty = t.get("difficulty", "")
                break

    return templates.TemplateResponse(
        request,
        "task_replay.html",
        {
            "active_page": "task",
            "active_task_id": task_id,
            "active_run_id": selected_run.run_id,
            "task_id": task_id,
            "run": selected_run,
            "all_runs": all_runs,
            "runs": all_runs,
            "trace": trace,
            "steps": steps,
            "planner_calls": planner_calls,
            "v0_meta": v0_meta,
            "task_input": task_input,
            "knowledge_html": knowledge_html,
            "pred": pred,
            "gold": gold,
            "diff": diff,
            "score_info": score_info,
            "difficulty": difficulty,
        },
    )


# ---------------------------------------------------------------------------
# P5 Eval reports — EVAL_PLAN_30D §1 五类指标视图
# ---------------------------------------------------------------------------

@app.get("/eval", response_class=HTMLResponse)
def eval_index(request: Request, base: str = "", challenger: str = ""):
    reports = discover_eval_reports()
    versions = list(reports.keys())
    base_id = base or (versions[0] if versions else "")
    ch_id = challenger or (versions[1] if len(versions) > 1 else base_id)

    base_report = reports.get(base_id)
    ch_report = reports.get(ch_id)

    diff_md = None
    diff_html = None
    if base_report and ch_report and base_id != ch_id:
        from src.eval.eval_diff import render_diff
        diff_md = render_diff(base_report, ch_report)
        diff_html = md_to_html(diff_md)

    return templates.TemplateResponse(
        request,
        "eval.html",
        {
            "active_page": "eval",
            "active_task_id": None,
            "active_run_id": None,
            "runs": discover_runs(),
            "reports": reports,
            "versions": versions,
            "base_id": base_id,
            "challenger_id": ch_id,
            "base_report": base_report,
            "ch_report": ch_report,
            "diff_md": diff_md,
            "diff_html": diff_html,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="agent-diagnose dev runner")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    import uvicorn

    uvicorn.run("agent_diagnose.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
