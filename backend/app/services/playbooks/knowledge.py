"""What Vocify knows about the company, once (layer 2 of the three-layer playbook model).

ICP and personas, who is not a fit, buying signals, the value story, differentiators, customer
cases, competitors, pricing and negotiation, notes. It is context for the copilot, the brief, the
follow-up and Ask; it never scores a call. Unlike a playbook it has no draft: a save takes effect
at once.

Pure and DB-free. `normalize_knowledge` is the one shape everything stores and returns (every key
always present, unknown keys dropped, strings trimmed and clipped, lists capped), so an API save
and a model's answer go through the same door. `merge_knowledge` is how a document adds to what a
Head of Sales already has without overwriting what they edited.
"""

from __future__ import annotations

import re
from typing import Any, Optional

MAX_LONG = 1500   # the free-text blocks: icp, value story, pricing, notes...
MAX_SHORT = 300   # every field inside a list item, and each differentiator
MAX_ITEMS = 12    # per list

TEXT_FIELDS: tuple[str, ...] = ("icp", "bad_fit", "value_short", "value_long", "pricing", "notes")

# list -> (its fields in order, the field that identifies an item: an item without it is dropped
# and two items with the same one (case-insensitive) are the same item). Each item is its name and
# ONE line, the one the copilot and briefs use: what a persona cares about, what to do on a buying
# signal, what a customer achieved, how to win against a competitor. Older extra fields (language,
# number, landmines...) are dropped on read and on the next save.
LIST_FIELDS: dict[str, tuple[tuple[str, ...], str]] = {
    "personas": (("name", "cares_about"), "name"),
    "triggers": (("signal", "how_to_use"), "signal"),
    "proofs": (("customer", "change"), "customer"),
    "competitors": (("name", "how_to_talk"), "name"),
}
# Order of `sections` and of the keys in the stored data: how the company page reads.
SECTION_ORDER: tuple[str, ...] = (
    "icp", "bad_fit", "personas", "triggers", "value_short", "value_long",
    "differentiators", "proofs", "competitors", "pricing", "notes",
)


class StaleKnowledgeError(Exception):
    """The company's knowledge was saved by someone else since the caller loaded it: its
    `base_updated_at` no longer matches. The API answers 409 `stale_knowledge`."""

    code = "stale_knowledge"

    def __init__(self) -> None:
        super().__init__("stale_knowledge")


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    if space >= limit * 0.6:
        cut = cut[:space]
    return cut.rstrip(" ,;:-—–")


def _scalar(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return ""
    return str(value)


def _short(value: Any, limit: int = MAX_SHORT) -> str:
    return _clip(" ".join(_scalar(value).split()), limit)


def _long(value: Any) -> str:
    """Trimmed, whitespace tidied inside each line, at most one blank line in a row (the
    Head of Sales's own line breaks stay), cut to MAX_LONG."""
    lines = [" ".join(line.split()) for line in _scalar(value).replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return _clip(text, MAX_LONG)


def _item(raw: Any, fields: tuple[str, ...], identity: str) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    item = {name: _short(raw.get(name)) for name in fields}
    return item if item[identity] else None


def _identity(item: dict, identity: str) -> str:
    return str(item.get(identity) or "").casefold()


def empty_knowledge() -> dict:
    return normalize_knowledge({})


def normalize_knowledge(raw: Any) -> dict:
    """Any input -> the stored shape. Unknown keys are dropped, strings trimmed and clipped
    (MAX_LONG for the blocks, MAX_SHORT inside items), lists capped at MAX_ITEMS; an item
    without its name/customer/signal is dropped and a repeated one (case-insensitive) is
    kept once, first wins. Never raises: a value of the wrong type is an empty one."""
    raw = raw if isinstance(raw, dict) else {}
    data: dict = {}
    for key in SECTION_ORDER:
        value = raw.get(key)
        if key in TEXT_FIELDS:
            data[key] = _long(value)
        elif key == "differentiators":
            seen: set[str] = set()
            items: list = []
            for entry in value if isinstance(value, list) else []:
                text = _short(entry)
                if text and text.casefold() not in seen:
                    seen.add(text.casefold())
                    items.append(text)
            data[key] = items[:MAX_ITEMS]
        else:
            fields, identity = LIST_FIELDS[key]
            seen = set()
            items = []
            for entry in value if isinstance(value, list) else []:
                item = _item(entry, fields, identity)
                if item is None or _identity(item, identity) in seen:
                    continue
                seen.add(_identity(item, identity))
                items.append(item)
            data[key] = items[:MAX_ITEMS]
    return data


def sections(knowledge: Any) -> list[str]:
    """The keys that hold something, in page order."""
    data = knowledge if isinstance(knowledge, dict) else {}
    return [key for key in SECTION_ORDER if data.get(key)]


def merge_knowledge(existing: Any, incoming: Any) -> tuple[dict, list[str]]:
    """What a document adds to what the company already has -> (merged, filled).

    - a text is filled only when the existing one is empty (what the Head of Sales wrote is
      never overwritten);
    - a list only grows: incoming items are appended unless one with the same
      name / customer / signal (case-insensitive) is already there, up to MAX_ITEMS;
      differentiators are deduplicated the same way;
    - `filled` names the keys that changed, in page order."""
    merged = normalize_knowledge(existing)
    new = normalize_knowledge(incoming)
    filled: list[str] = []
    for key in SECTION_ORDER:
        if key in TEXT_FIELDS:
            if not merged[key] and new[key]:
                merged[key] = new[key]
                filled.append(key)
            continue
        identity = None if key == "differentiators" else LIST_FIELDS[key][1]
        known = {(_identity(i, identity) if identity else i.casefold()) for i in merged[key]}
        added = False
        for item in new[key]:
            marker = _identity(item, identity) if identity else item.casefold()
            if marker in known or len(merged[key]) >= MAX_ITEMS:
                continue
            known.add(marker)
            merged[key].append(item)
            added = True
        if added:
            filled.append(key)
    return merged, filled
