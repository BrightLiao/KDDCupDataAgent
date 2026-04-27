"""单值归一化器 — scorer 与提交端共用，保证 multiset 比对一致。

规则按 [比赛简介.md §6.5] / [方案调研综述.md §7.1]：
- None / nan / "" / "none" / "null" / "n/a" → ""
- bool → "1" / "0"
- 整数 → str(int)
- 浮点 / 数字字符串 → 2 位小数（去尾零）；整数表示去 ".0"
- 日期（YYYY-MM-DD / YYYY/M/D / YYYY.M.D，可选时间后缀） → ISO YYYY-MM-DD
- 文本 → strip + 折叠多空格

任何修改必须同时通过 v0 的 `tests/test_normalize_parity.py`，否则 scorer 与提交端会出现静默漂移。
"""
from __future__ import annotations

import math
import re

ISO_DATE_RE = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[T ].*)?$")


def normalize_value(v) -> str:
    """归一化单值到字符串。"""
    if v is None:
        return ""
    if isinstance(v, float):
        if math.isnan(v):
            return ""
        return f"{round(v, 2):.2f}".rstrip("0").rstrip(".") or "0"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, int):
        return str(v)
    s = str(v).strip()
    if s == "" or s.lower() in ("nan", "none", "null", "n/a"):
        return ""
    try:
        x = float(s)
        if math.isnan(x):
            return ""
        if x == int(x) and "." not in s and "e" not in s.lower():
            return str(int(x))
        return f"{round(x, 2):.2f}".rstrip("0").rstrip(".") or "0"
    except ValueError:
        pass
    m = ISO_DATE_RE.match(s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return " ".join(s.split())
