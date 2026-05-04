"""Env-driven OpenAI-compat model adapter for the submission container.

Hidden-test harness injects MODEL_API_URL / MODEL_API_KEY / MODEL_NAME.
Local dev falls back to BAILIAN_API_KEY + dashscope endpoint.
Critical: max_retries=0 —— under --network=none the OpenAI sdk default 2-retry
would loop ~30s+ per task. Fail fast and let entrypoint write error placeholder CSV.
"""
from __future__ import annotations

import os

from openai import APIError, OpenAI

from data_agent_baseline.agents.model import ModelAdapter, ModelMessage

_BAILIAN_DEV_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def _resolve_env() -> tuple[str, str, str]:
    base_url = os.environ.get("MODEL_API_URL") or _BAILIAN_DEV_URL
    api_key = os.environ.get("MODEL_API_KEY") or os.environ.get("BAILIAN_API_KEY")
    model_name = os.environ.get("MODEL_NAME")

    missing: list[str] = []
    if not api_key:
        missing.append("MODEL_API_KEY (or BAILIAN_API_KEY for local dev)")
    if not model_name:
        missing.append("MODEL_NAME")
    if missing:
        raise SystemExit(f"[model_client] missing env: {', '.join(missing)}")

    return base_url, api_key, model_name


class EnvModelAdapter(ModelAdapter):
    """Env-driven, fail-fast (max_retries=0) OpenAI-compat adapter."""

    def __init__(self, *, temperature: float = 0.0, seed: int | None = None) -> None:
        self.api_base, self.api_key, self.model = _resolve_env()
        self.temperature = temperature
        self.seed = seed

    def complete(self, messages: list[ModelMessage]) -> str:
        client = OpenAI(api_key=self.api_key, base_url=self.api_base, max_retries=0)
        kwargs: dict = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": self.temperature,
        }
        if self.seed is not None:
            kwargs["seed"] = self.seed
        try:
            response = client.chat.completions.create(**kwargs)
        except APIError as exc:
            raise RuntimeError(f"Model request failed: {exc}") from exc
        choice = response.choices[0].message.content if response.choices else None
        return choice or ""
