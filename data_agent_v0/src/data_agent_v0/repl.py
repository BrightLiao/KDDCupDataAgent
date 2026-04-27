"""持久 Python REPL — 一个 task 一个 worker 子进程，跨步共享 namespace。

L1 (CodeAct) + L2 (preload) 共用基础设施。submit() 通过哨兵变量
`__submitted_answer__` 通知主进程终止，避免在 worker 里 raise SystemExit
导致 REPL 死掉。"""
from __future__ import annotations

import io
import multiprocessing as mp
import os
import signal
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ReplResult:
    event: str  # "ok" | "submit" | "error" | "timeout" | "fatal"
    stdout: str = ""
    stderr: str = ""
    traceback: str | None = None
    submitted: dict[str, Any] | None = None  # {columns, rows} when event == "submit"

    @property
    def ok(self) -> bool:
        return self.event in ("ok", "submit")

    def to_obs_dict(self, max_chars: int = 4000) -> dict[str, Any]:
        out = self.stdout
        err = self.stderr
        if len(out) > max_chars:
            out = out[: max_chars - 20] + "\n... [truncated] ..."
        if len(err) > max_chars:
            err = err[: max_chars - 20] + "\n... [truncated] ..."
        d: dict[str, Any] = {"ok": self.ok, "event": self.event}
        if out:
            d["stdout"] = out
        if err:
            d["stderr"] = err
        if self.traceback:
            tb = self.traceback
            if len(tb) > max_chars:
                tb = tb[: max_chars - 20] + "\n... [truncated] ..."
            d["traceback"] = tb
        if self.event == "submit":
            d["submitted_shape"] = {
                "columns": len(self.submitted["columns"]) if self.submitted else 0,
                "rows": len(self.submitted["rows"]) if self.submitted else 0,
            }
        return d


def _build_default_namespace(
    context_root: Path,
    shape_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """worker 内构造默认命名空间（pandas / numpy / json / sqlite3 / submit）。

    L2 的 preload_into_namespace 会在此基础上追加 df_<name> / json_<name> / conn_<name>。
    submit() 内置 L3 校验 + 归一化（与 scorer 共享 normalize_value）。
    """
    import json as _json  # noqa: F401
    import sqlite3 as _sqlite3  # noqa: F401
    from pathlib import Path as _Path

    import numpy as _np  # noqa: F401
    import pandas as _pd  # noqa: F401

    # L3: lazy import inside worker (sys.path setup happens in output.normalize)
    from data_agent_v0.output.normalize import normalize_table
    from data_agent_v0.output.shape import validate_submit

    ns: dict[str, Any] = {
        "__name__": "__codeact_repl__",
        "__builtins__": __builtins__,
        "context_root": context_root,
        "Path": _Path,
        "pd": _pd,
        "np": _np,
        "json": _json,
        "sqlite3": _sqlite3,
    }

    def _submit(value: Any) -> None:
        # Step 1: extract columns/rows
        if hasattr(value, "columns") and hasattr(value, "values"):
            cols = [str(c) for c in value.columns]
            rows = [list(row) for row in value.values.tolist()]
        elif isinstance(value, dict) and "columns" in value and "rows" in value:
            cols = [str(c) for c in value["columns"]]
            rows = [list(r) for r in value["rows"]]
        else:
            raise TypeError(
                "submit() expects pandas DataFrame or {'columns': [...], 'rows': [[...]]}"
            )

        # Step 2: shape validation (may truncate rows in-place)
        ok, err, info = validate_submit(cols, rows, shape_spec)
        if not ok:
            # Surface as exception → LLM sees in next observation, can retry
            raise ValueError(err)

        # Step 3: cell-level normalization (single source of truth with scorer)
        norm_cols, norm_rows = normalize_table(cols, rows)

        ns["__submitted_answer__"] = {
            "columns": norm_cols,
            "rows": norm_rows,
            "validation": info,
        }

    ns["submit"] = _submit
    return ns


def _exec_with_timeout(code: str, namespace: dict[str, Any], timeout_seconds: int) -> None:
    """SIGALRM-based timeout (Unix). exec is synchronous so signal interrupts it."""

    def _handler(signum, frame):  # noqa: ARG001
        raise TimeoutError(f"Code execution exceeded {timeout_seconds}s")

    old = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(int(timeout_seconds))
    try:
        exec(code, namespace, namespace)  # noqa: S102
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def _worker_main(
    context_root_str: str,
    cmd_q: mp.Queue,
    result_q: mp.Queue,
    preload_enabled: bool,
    preload_max_csv_mb: int,
    shape_spec: dict[str, Any] | None,
) -> None:
    context_root = Path(context_root_str)
    try:
        os.chdir(context_root_str)
        namespace = _build_default_namespace(context_root, shape_spec=shape_spec)

        # L2 preload (lazy import so Step 2 can run without preload module)
        preload_summary: dict[str, Any] = {}
        knowledge: dict[str, str] = {}
        if preload_enabled:
            try:
                from data_agent_v0.preload import preload_into_namespace  # type: ignore

                preload_summary, knowledge = preload_into_namespace(
                    context_root, namespace, max_csv_size_mb=preload_max_csv_mb
                )
            except Exception:  # noqa: BLE001
                preload_summary = {"_error": traceback.format_exc()}

        result_q.put({"event": "ready", "summary": preload_summary, "knowledge": knowledge})

        while True:
            cmd = cmd_q.get()
            if cmd is None:
                break
            code = cmd.get("code", "")
            timeout = int(cmd.get("timeout", 60))

            stdout_buf = io.StringIO()
            stderr_buf = io.StringIO()
            try:
                with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                    _exec_with_timeout(code, namespace, timeout)
            except TimeoutError as exc:
                result_q.put(
                    {
                        "event": "timeout",
                        "stdout": stdout_buf.getvalue(),
                        "stderr": stderr_buf.getvalue(),
                        "traceback": str(exc),
                    }
                )
                continue
            except SystemExit:
                # Treat SystemExit inside user code as benign (not a submit signal)
                pass
            except BaseException:  # noqa: BLE001
                result_q.put(
                    {
                        "event": "error",
                        "stdout": stdout_buf.getvalue(),
                        "stderr": stderr_buf.getvalue(),
                        "traceback": traceback.format_exc(),
                    }
                )
                continue

            event = "ok"
            submitted = None
            if "__submitted_answer__" in namespace:
                submitted = namespace.pop("__submitted_answer__")
                event = "submit"

            result_q.put(
                {
                    "event": event,
                    "stdout": stdout_buf.getvalue(),
                    "stderr": stderr_buf.getvalue(),
                    "submitted": submitted,
                }
            )
    except BaseException:  # noqa: BLE001
        result_q.put({"event": "fatal", "traceback": traceback.format_exc()})


class TaskRepl:
    """每 task 一个长驻 REPL 子进程。"""

    def __init__(
        self,
        context_root: Path,
        *,
        preload_enabled: bool = False,
        preload_max_csv_mb: int = 500,
        ready_timeout: int = 120,
        shape_spec: dict[str, Any] | None = None,
    ) -> None:
        self.context_root = context_root.resolve()
        self.shape_spec = shape_spec
        ctx = mp.get_context("spawn")  # consistent across darwin/linux
        self._cmd_q = ctx.Queue()
        self._result_q = ctx.Queue()
        self._proc = ctx.Process(
            target=_worker_main,
            args=(
                str(self.context_root),
                self._cmd_q,
                self._result_q,
                preload_enabled,
                preload_max_csv_mb,
                shape_spec,
            ),
            daemon=True,
        )
        self._closed = False
        self._proc.start()
        self._ready_payload = self._wait_ready(ready_timeout)

    def _wait_ready(self, timeout: int) -> dict[str, Any]:
        try:
            payload = self._result_q.get(timeout=timeout)
        except Exception as exc:  # queue.Empty subclass
            self.shutdown()
            raise RuntimeError(f"REPL did not become ready within {timeout}s") from exc
        if payload.get("event") == "fatal":
            tb = payload.get("traceback", "")
            self.shutdown()
            raise RuntimeError(f"REPL worker crashed during init: {tb}")
        if payload.get("event") != "ready":
            self.shutdown()
            raise RuntimeError(f"Unexpected REPL ready payload: {payload}")
        return payload

    @property
    def preload_summary(self) -> dict[str, Any]:
        return dict(self._ready_payload.get("summary") or {})

    @property
    def knowledge(self) -> dict[str, str]:
        return dict(self._ready_payload.get("knowledge") or {})

    def execute(self, code: str, *, timeout: int = 60) -> ReplResult:
        if self._closed:
            raise RuntimeError("REPL is closed")
        if not self._proc.is_alive():
            return ReplResult(event="fatal", traceback="REPL worker is no longer alive")
        self._cmd_q.put({"code": code, "timeout": timeout})
        # Allow some headroom: subprocess timeout > code timeout to surface SIGALRM.
        try:
            payload = self._result_q.get(timeout=timeout + 30)
        except Exception:  # queue.Empty
            return ReplResult(
                event="fatal",
                traceback=f"REPL did not respond within {timeout + 30}s; worker may be stuck",
            )
        ev = payload.get("event", "error")
        return ReplResult(
            event=ev,
            stdout=payload.get("stdout", "") or "",
            stderr=payload.get("stderr", "") or "",
            traceback=payload.get("traceback"),
            submitted=payload.get("submitted"),
        )

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._cmd_q.put_nowait(None)
        except Exception:  # noqa: BLE001
            pass
        self._proc.join(timeout=1.0)
        if self._proc.is_alive():
            self._proc.terminate()
            self._proc.join(timeout=1.0)
        if self._proc.is_alive():
            self._proc.kill()
            self._proc.join()

    def __enter__(self) -> "TaskRepl":
        return self

    def __exit__(self, *args) -> None:  # noqa: ANN002
        self.shutdown()
