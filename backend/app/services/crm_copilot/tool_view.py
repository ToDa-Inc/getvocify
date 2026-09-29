"""What the model reads of a tool result: the facts, without the bookkeeping.

The full payload still feeds the number check, the evidence list and the coverage note. The model only pays
tokens for what it can use: no timestamps to the microsecond, no null or empty fields on a row, no internal
ids it would copy into an answer, and no second copy of quotes it already has inline.
"""

from __future__ import annotations

import json
import re
from typing import Any

MAX_CHARS = 12_000
_DROP_KEYS = {"observed_at", "period_defaulted", "memo_id"}
_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?$")


def _clean(value: Any, in_row: bool = False) -> Any:
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key in _DROP_KEYS:
                continue
            item = _clean(item)
            if in_row and item in (None, "", [], {}):
                continue
            out[key] = item
        return out
    if isinstance(value, list):
        return [_clean(item, in_row=isinstance(item, dict)) for item in value]
    if isinstance(value, str) and _DATETIME.match(value):
        return value[:10]
    return value


def _quotes_are_inline(body: dict) -> bool:
    evidence = body.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return False
    rest = json.dumps({k: v for k, v in body.items() if k != "evidence"}, ensure_ascii=False, default=str)
    return all(isinstance(e, dict) and e.get("id") and e["id"] in rest for e in evidence)


def model_view(payload: Any) -> str:
    body = _clean(payload)
    if isinstance(body, dict) and _quotes_are_inline(body):
        body.pop("evidence")
    text = json.dumps(body, separators=(",", ":"), ensure_ascii=False, default=str)
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS]
