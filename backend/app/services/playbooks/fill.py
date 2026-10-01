"""Fill with AI: the manager says, in their own words, what to add, change, complete or remove in a
playbook or in "Vuestra empresa", and Vocify applies it. The way to edit after the first import
without filling a form.

One model call returns only the CHANGES (never the whole document), and deterministic code applies
them, so a request about one objection can never rewrite the rest of the playbook:

- a step or a qualification criterion is changed by its 1-based `index` in the current list and
  added with `index: null`; an objection is found by category (a custom one by its label); a list
  item of the company notes by its name / customer / signal. A field the model leaves empty is
  left as it is;
- everything is clipped to the limits the editor saves with and loses the markdown it may copy;
  a step criterion that names an attitude is emptied (the editor asks for one), as when
  structuring;
- the company notes keep the structuring guards: a new competitor the request does not name is
  dropped, and a customer result with a figure it does not contain is emptied;
- the result goes through the same normalizers as a save, so it always saves.

A playbook change is returned, not saved: the editor puts it in its draft (it autosaves, keeps the
conflict check and nothing reaches the team until it is published). Company notes have no draft,
so the API saves them with the caller's `base_updated_at`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from app.services.playbooks.knowledge import (
    LIST_FIELDS,
    MAX_ITEMS,
    TEXT_FIELDS,
    normalize_knowledge,
)
from app.services.playbooks.structure import (
    _ask,
    _client,
    _deaccent,
    _digits,
    _fold,
    call_type_label,
    detect_language,
    goal_label,
    timeout_for,
)
from app.services.playbooks.structured import (
    CUSTOM_CATEGORY,
    MAX_CRITERIA,
    MAX_CRITERION,
    MAX_CRITERION_LABEL,
    MAX_CRITERION_TEXT,
    MAX_CUSTOM_OBJECTIONS,
    MAX_EXAMPLE,
    MAX_GUIDANCE,
    MAX_LABEL,
    MAX_OBJECTION_LABEL,
    MAX_STEPS,
    MAX_TRIGGER,
    OBJECTION_CATEGORIES,
    clip_text,
    normalize_objections,
    normalize_qualification,
    normalize_steps,
    objection_view,
    strip_markdown,
)
from app.services.text_guard import generic_criterion

logger = logging.getLogger(__name__)

PLAYBOOK_PROMPT_VERSION = "playbook_fill_v1"
COMPANY_PROMPT_VERSION = "company_fill_v1"
_PROMPTS = Path(__file__).resolve().parents[2] / "prompts"
MAX_REQUEST_CHARS = 20_000


class FillError(Exception):
    """The model failed, timed out or answered something that cannot be applied. The API answers
    422 `fill_failed`: the request can be tried again, nothing was changed."""


@lru_cache(maxsize=2)
def _prompt(version: str) -> str:
    return (_PROMPTS / f"{version}.md").read_text(encoding="utf-8")


def _list(value: Any) -> list[dict]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _text(raw: dict, name: str, limit: int) -> str:
    return clip_text(strip_markdown(raw.get(name)), limit)


def _index(value: Any, size: int) -> Optional[int]:
    """The model's 1-based index as a 0-based one, or None when it names nothing that exists."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    index = int(value) - 1
    return index if 0 <= index < size else None


def _indexes(value: Any, size: int) -> set[int]:
    return {i for i in (_index(v, size) for v in (value if isinstance(value, list) else [])) if i is not None}


async def _call(messages: list[dict], source: str) -> dict:
    timeout = timeout_for(source)
    try:
        answer = await asyncio.wait_for(_ask(_client(None), messages, timeout), timeout + 5)
    except Exception as exc:
        logger.warning("fill: model call failed: %s", type(exc).__name__)
        raise FillError("model") from exc
    if not isinstance(answer, dict):
        raise FillError("shape")
    return answer


# --- one call type's playbook ------------------------------------------------------------------


def _objection_key(item: dict) -> str:
    category = str(item.get("category") or "").lower()
    if category == CUSTOM_CATEGORY:
        return f"custom:{str(item.get('label') or '').strip().casefold()}"
    return category


def _apply_items(current: list[dict], ops: Any, removals: Any, fields: dict[str, int], title: str, cap: int) -> tuple[list[dict], int]:
    """Steps and qualification criteria: update by index, add with index null, remove by index.
    Indexes always refer to the list as it was sent. -> (the new list, how many changed)."""
    items = [dict(item) for item in current]
    added: list[dict] = []
    changed = 0
    for raw in _list(ops):
        values = {name: _text(raw, name, limit) for name, limit in fields.items()}
        given = raw.get("index")
        index = _index(given, len(items))
        if given is not None and index is None:
            continue  # names an item that doesn't exist: not an addition
        if index is not None:
            update = {name: value for name, value in values.items() if value}
            if update:
                items[index].update(update)
                items[index]["_changed"] = set(update)
                changed += 1
        elif values[title] and len(items) + len(added) < cap:
            added.append({**{name: value for name, value in values.items() if value}, "_changed": set(values)})
            changed += 1
    removed = _indexes(removals, len(items))
    changed += len(removed)
    return [item for i, item in enumerate(items) if i not in removed] + added, changed


def restrict_to(ops: Any, scope: Optional[dict]) -> Any:
    """A "Completar" asks about ONE item: whatever else the model wrote is dropped, so completing
    one answer can never rewrite the others. `scope`: {"steps": [1-based index]} |
    {"qualification": [index]} | {"objections": [{"category", "label"?}]}; None = no restriction."""
    if not scope or not isinstance(ops, dict):
        return ops
    steps = {int(i) for i in scope.get("steps") or [] if isinstance(i, (int, float))}
    criteria = {int(i) for i in scope.get("qualification") or [] if isinstance(i, (int, float))}
    objections = {
        _objection_key({"category": str(o.get("category") or "").lower(), "label": str(o.get("label") or "")})
        for o in _list(scope.get("objections"))
    }
    return {
        **ops,
        "steps": [o for o in _list(ops.get("steps")) if o.get("index") in steps],
        "qualification": [o for o in _list(ops.get("qualification")) if o.get("index") in criteria],
        "objections": [
            o for o in _list(ops.get("objections"))
            if _objection_key({"category": str(o.get("category") or "").lower(), "label": str(o.get("label") or "")}) in objections
        ],
        "remove_steps": [],
        "remove_qualification": [],
        "remove_objections": [],
    }


def _scope_line(scope: Optional[dict]) -> str:
    if not scope:
        return ""
    parts = [f"step {i}" for i in scope.get("steps") or []]
    parts += [f"qualification {i}" for i in scope.get("qualification") or []]
    parts += [
        f'objection {o.get("category")}' + (f' "{o["label"]}"' if o.get("label") else "")
        for o in _list(scope.get("objections"))
    ]
    return f"\n\nChange ONLY: {', '.join(parts)}. Leave everything else exactly as it is." if parts else ""


def apply_playbook_changes(current: dict, ops: Any) -> dict:
    """The current editor content ({steps, objections, qualification}, as the editor saves it) with
    the model's changes applied -> {steps, objections, qualification, changes}. Always saveable."""
    ops = ops if isinstance(ops, dict) else {}
    steps, step_changes = _apply_items(
        _list(current.get("steps")), ops.get("steps"), ops.get("remove_steps"),
        {"label": MAX_LABEL, "criterion": MAX_CRITERION, "example": MAX_EXAMPLE}, "label", MAX_STEPS,
    )
    for step in steps:
        # An attitude can't be checked in a transcript: leave it for the manager, as structuring does.
        if "criterion" in step.pop("_changed", set()) and generic_criterion(step.get("criterion", "")):
            step["criterion"] = ""
    criteria, criterion_changes = _apply_items(
        _list(current.get("qualification")), ops.get("qualification"), ops.get("remove_qualification"),
        {"label": MAX_CRITERION_LABEL, "good": MAX_CRITERION_TEXT},
        "label", MAX_CRITERIA,
    )
    for item in criteria:
        item.pop("_changed", None)

    objections = [dict(item) for item in _list(current.get("objections"))]
    by_key = {_objection_key(item): item for item in objections}
    objection_changes = 0
    for raw in _list(ops.get("objections")):
        category = str(raw.get("category") or "").strip().lower()
        if category not in OBJECTION_CATEGORIES and category != CUSTOM_CATEGORY:
            continue
        values = {
            "label": _text(raw, "label", MAX_OBJECTION_LABEL) if category == CUSTOM_CATEGORY else "",
            "trigger": _text(raw, "trigger", MAX_TRIGGER),
            "guidance": _text(raw, "guidance", MAX_GUIDANCE),
        }
        key = _objection_key({"category": category, "label": values["label"]})
        update = {name: value for name, value in values.items() if value}
        if key in by_key:
            if update:
                by_key[key].update(update)
                objection_changes += 1
            continue
        customs = sum(1 for item in objections if item.get("category") == CUSTOM_CATEGORY)
        if category == CUSTOM_CATEGORY and (not values["label"] or customs >= MAX_CUSTOM_OBJECTIONS):
            continue
        if category != CUSTOM_CATEGORY and not values["guidance"]:
            continue  # a fixed category exists only with its answer
        entry = {"category": category, "guidance": values["guidance"], **update}
        objections.append(entry)
        by_key[key] = entry
        objection_changes += 1
    gone = {
        _objection_key({"category": str(r.get("category") or "").lower(), "label": str(r.get("label") or "")})
        for r in _list(ops.get("remove_objections"))
    }
    kept = [item for item in objections if _objection_key(item) not in gone]
    objection_changes += len(objections) - len(kept)

    # The shapes every save goes through: if these pass, the draft saves.
    if steps:
        normalize_steps([{**s, "criterion": s.get("criterion") or s["label"]} for s in steps])
    entries = normalize_objections(kept)
    normalize_qualification(criteria)
    return {
        "steps": [
            {key: step[key] for key in ("step_id", "label", "criterion", "example") if step.get(key) is not None}
            for step in steps
        ],
        "objections": [objection_view(entry) for entry in entries],
        "qualification": [
            {key: item[key] for key in ("criterion_id", "label", "good") if item.get(key)} for item in criteria
        ],
        "changes": step_changes + criterion_changes + objection_changes,
    }


def _current_block(current: dict) -> str:
    steps = [
        {"index": i, "label": s.get("label"), "criterion": s.get("criterion"), "example": s.get("example") or None}
        for i, s in enumerate(_list(current.get("steps")), start=1)
    ]
    criteria = [
        {"index": i, "label": c.get("label"), "good": c.get("good") or None}
        for i, c in enumerate(_list(current.get("qualification")), start=1)
    ]
    return json.dumps(
        {"steps": steps, "qualification": criteria, "objections": _list(current.get("objections"))},
        ensure_ascii=False,
    )


async def fill_playbook(
    motion_key: str, request: str, current: dict, company_text: str = "", scope: Optional[dict] = None,
) -> dict:
    """The manager's request applied to one call type's current content; with `scope`, only to that
    item (see restrict_to). Raises FillError."""
    request = (request or "").strip()[:MAX_REQUEST_CHARS]
    sample = " ".join([request] + [str(s.get("criterion") or "") for s in _list(current.get("steps"))])
    lang = detect_language(sample)
    user = (
        f"Call type: {call_type_label(motion_key, lang)} (key: {motion_key})\n"
        f"Goal: {goal_label(motion_key, lang)}\n"
        f"Company language: {'English' if lang == 'en' else 'Spanish'}\n\n"
        f"What the company says about itself:\n{company_text.strip() or '(nothing yet)'}\n\n"
        f"Current playbook:\n{_current_block(current)}\n\n"
        f'Request:\n"""\n{request}\n"""{_scope_line(scope)}'
    )
    answer = await _call([{"role": "system", "content": _prompt(PLAYBOOK_PROMPT_VERSION)}, {"role": "user", "content": user}], request)
    try:
        result = apply_playbook_changes(current, restrict_to(answer, scope))
    except Exception as exc:  # PlaybookDraftError, or a shape the normalizers reject
        logger.warning("fill: playbook changes not applicable: %s", exc)
        raise FillError("apply") from exc
    return {**result, "summary": clip_text(answer.get("summary"), 200)}


# --- the company's notes ("Vuestra empresa") ---------------------------------------------------


def _mark(changed: list[str], key: str) -> None:
    if key not in changed:
        changed.append(key)


def _named_in(name: str, plain_source: str) -> bool:
    return _deaccent(_fold(name)) in plain_source


def restrict_company(ops: Any, scope: Optional[dict]) -> Any:
    """A "Completar" in the company notes asks about one item ({"list", "name"}) or some text
    fields ({"texts": [...]}): whatever else the model wrote is dropped, removals included."""
    if not scope or not isinstance(ops, dict):
        return ops
    patch = ops.get("set") if isinstance(ops.get("set"), dict) else {}
    kept: dict = {}
    texts = {key for key in scope.get("texts") or [] if key in TEXT_FIELDS}
    for key in texts:
        if patch.get(key):
            kept[key] = patch[key]
    key = scope.get("list")
    if key in LIST_FIELDS:
        identity = LIST_FIELDS[key][1]
        name = str(scope.get("name") or "").strip().casefold()
        kept[key] = [item for item in _list(patch.get(key)) if str(item.get(identity) or "").strip().casefold() == name]
    return {**ops, "set": kept, "remove": {}}


def apply_company_changes(existing: Any, ops: Any, source: str) -> tuple[dict, list[str]]:
    """The stored notes with the model's changes applied -> (notes, keys that changed). `source`
    is what the manager said plus what was already written: a new competitor must be named in it
    and the figures in a customer result must be in it."""
    data = normalize_knowledge(existing)
    ops = ops if isinstance(ops, dict) else {}
    patch = ops.get("set") if isinstance(ops.get("set"), dict) else {}
    plain = _deaccent(_fold(source))
    digits = _digits(source)
    changed: list[str] = []

    incoming = normalize_knowledge({key: strip_markdown(value) if isinstance(value, str) else value for key, value in patch.items()})
    for key in TEXT_FIELDS:
        if incoming[key] and incoming[key] != data[key]:
            data[key] = incoming[key]
            changed.append(key)
    known = {item.casefold() for item in data["differentiators"]}
    for item in incoming["differentiators"]:
        if item.casefold() not in known and len(data["differentiators"]) < MAX_ITEMS:
            data["differentiators"].append(item)
            known.add(item.casefold())
            _mark(changed, "differentiators")

    for key, (fields, identity) in LIST_FIELDS.items():
        by_name = {str(item[identity]).casefold(): item for item in data[key]}
        for item in incoming[key]:
            item = {name: strip_markdown(value) for name, value in item.items()}
            if key == "proofs" and not _digits(item.get("change", "")) <= digits:
                item["change"] = ""  # a result with a figure nobody gave
            target = by_name.get(str(item[identity]).casefold())
            update = {name: value for name, value in item.items() if value and name != identity}
            if target is not None:
                if any(target.get(name) != value for name, value in update.items()):
                    target.update(update)
                    _mark(changed, key)
                continue
            if key == "competitors" and not _named_in(item["name"], plain):
                continue  # a competitor nobody named
            if len(data[key]) < MAX_ITEMS:
                data[key].append(item)
                by_name[str(item[identity]).casefold()] = item
                _mark(changed, key)

    remove = ops.get("remove") if isinstance(ops.get("remove"), dict) else {}
    for key in (*LIST_FIELDS, "differentiators"):
        names = {str(name).strip().casefold() for name in (remove.get(key) or []) if isinstance(name, str)}
        if not names:
            continue
        identity = LIST_FIELDS[key][1] if key in LIST_FIELDS else None
        before = len(data[key])
        data[key] = [
            item for item in data[key]
            if (str(item[identity]) if identity else item).casefold() not in names
        ]
        if len(data[key]) != before:
            _mark(changed, key)
    return normalize_knowledge(data), changed


def _knowledge_text(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False)


async def fill_company(request: str, existing: Any, product_context: str = "", scope: Optional[dict] = None) -> dict:
    """The manager's request applied to the company's notes (with `scope`, only to that part; see
    restrict_company) -> {knowledge, filled, summary}. Not saved here. Raises FillError."""
    request = (request or "").strip()[:MAX_REQUEST_CHARS]
    current = normalize_knowledge(existing)
    lang = detect_language(request)
    user = (
        f"Company language: {'English' if lang == 'en' else 'Spanish'}\n\n"
        f"Product description:\n{product_context.strip() or '(none)'}\n\n"
        f"Current notes:\n{_knowledge_text(current)}\n\n"
        f'Request:\n"""\n{request}\n"""'
    )
    answer = await _call([{"role": "system", "content": _prompt(COMPANY_PROMPT_VERSION)}, {"role": "user", "content": user}], request)
    knowledge, filled = apply_company_changes(
        current, restrict_company(answer, scope), " ".join([request, _knowledge_text(current), product_context]),
    )
    return {"knowledge": knowledge, "filled": filled, "summary": clip_text(answer.get("summary"), 200)}
