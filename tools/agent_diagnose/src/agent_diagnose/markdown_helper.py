"""knowledge.md → safe HTML 渲染。"""
from __future__ import annotations

import markdown as _md


def md_to_html(text: str) -> str:
    return _md.markdown(
        text,
        extensions=["fenced_code", "tables", "sane_lists", "codehilite"],
    )
