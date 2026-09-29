"""Structure with AI: a manager's own material (pasted script, dictated notes, a PDF's text,
an audio transcript) becomes the steps and objection answers of one playbook.

One model call, with deterministic rules after it (the model is never trusted with a limit):

- the output is clipped to the limits in structured.py, never rejected, then goes through
  normalize_steps / normalize_objections, so what this returns always saves;
- at most MAX_AI_STEPS steps (more -> the first ones, reason "grouped");
- an `example` the source does not contain literally is dropped (an invented sentence
  would be presented as the manager's own words);
- a criterion that names an attitude ("genera confianza") cannot be judged in a transcript:
  the model is asked once more; if it still writes one, that step keeps its label and gets
  an EMPTY criterion, which the editor shows as "write when this counts as done". (The
  alternative, criterion == label as normalize_steps does, would be indistinguishable from
  a criterion the manager wrote.)
- if the model fails, times out or returns nothing usable, the deterministic line parser
  (a port of the frontend's parsePlaybookText) builds the steps and `fallback` is true.
  Structuring never blocks the manager.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.services.playbooks.motion import goal_for
from app.services.playbooks.structured import (
    MAX_CRITERION,
    MAX_EXAMPLE,
    MAX_GUIDANCE,
    MAX_LABEL,
    OBJECTION_CATEGORIES,
    clip_text,
    normalize_objections,
    normalize_steps,
    parse_playbook_text,
)
from app.services.text_guard import generic_criterion, generic_phrases

logger = logging.getLogger(__name__)

PROMPT_VERSION = "playbook_structure_v1"
_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / f"{PROMPT_VERSION}.md"

MAX_AI_STEPS = 7
# Same posture as the glossary hints: a short timeout and one attempt at the client. The
# Head of Sales waits on this call, so a slow model becomes the line parser, not a spinner.
TIMEOUT_S = 25.0
MAX_RETRIES = 0
TEMPERATURE = 0.2
MAX_SOURCE_CHARS = 40_000
# Fewer letters than this is "too short" to be a process ("llamamos y agendamos").
MIN_SOURCE_CHARS = 25

_llm: Any = None


def set_playbook_structure_llm(llm: Any) -> None:
    """Test seam (like set_playbook_transcriber): an object with `chat_json(messages, **kw)`,
    sync or async. None restores the real LLMClient."""
    global _llm
    _llm = llm


@lru_cache(maxsize=1)
def _system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


_TYPE_LABELS = {
    "discovery": {"es": "Llamada en frío (SDR)", "en": "Cold call (SDR)"},
    "inbound": {"es": "Lead inbound (SDR)", "en": "Inbound lead (SDR)"},
    "ae_discovery": {"es": "Discovery (AE)", "en": "Discovery (AE)"},
    "closing": {"es": "Demo y cierre (AE)", "en": "Demo and close (AE)"},
    "negotiation": {"es": "Propuesta y negociación (AE)", "en": "Proposal and negotiation (AE)"},
    "qualification": {"es": "Cualificación", "en": "Qualification"},
}
_GOALS = {
    "meeting_booked": {
        "es": "Reunión agendada con día y hora",
        "en": "A meeting booked with a day and time",
    },
    "proposal_and_close": {
        "es": "Siguiente paso con fecha: propuesta, prueba o firma",
        "en": "A next step with a date: proposal, trial or signature",
    },
}


def call_type_label(motion_key: str, lang: str) -> str:
    known = _TYPE_LABELS.get(motion_key)
    if known:
        return known["en" if lang == "en" else "es"]
    return f"«{motion_key}»" if lang != "en" else f'"{motion_key}"'


def goal_label(motion_key: str, lang: str) -> str:
    goal = goal_for(motion_key)
    if goal and goal in _GOALS:
        return _GOALS[goal]["en" if lang == "en" else "es"]
    return "not defined for this call type" if goal is None else goal


_EN_WORDS = frozenset(
    "the and to of you your we our is are for with that this then ask asks call calls "
    "customer prospect meeting first next if they them have has will can what how".split()
)
_ES_WORDS = frozenset(
    "el la los las de del que y en un una para con por se su sus nos es son llamada cliente "
    "prospecto reunión reunion primero luego después despues si les lo al como qué".split()
)


def detect_language(text: str, default: str = "es") -> str:
    """"es" or "en" from the source's own words: the document comes out in the language it
    was written in, whatever the app's language is."""
    words = re.findall(r"[a-záéíóúñü]+", (text or "").lower())[:400]
    if not words:
        return default
    en = sum(1 for word in words if word in _EN_WORDS)
    es = sum(1 for word in words if word in _ES_WORDS)
    if en > es:
        return "en"
    if es > en:
        return "es"
    return default


def _letters(text: str) -> int:
    return len(re.sub(r"[\W_]+", "", text or ""))


def _fold(text: str) -> str:
    normal = unicodedata.normalize("NFKC", text or "").casefold()
    return " ".join(re.sub(r"[\W_]+", " ", normal).split())


def _literal_in(example: str, folded_source: str) -> bool:
    folded = _fold(example)
    return bool(folded) and folded in folded_source


def _messages(source: str, motion_key: str, lang: str) -> list[dict]:
    body = source[:MAX_SOURCE_CHARS]
    user = (
        f"Call type: {call_type_label(motion_key, lang)} (key: {motion_key})\n"
        f"Goal: {goal_label(motion_key, lang)}\n"
        f"Company language: {'English' if lang == 'en' else 'Spanish'}\n\n"
        f'Source:\n"""\n{body}\n"""'
    )
    return [{"role": "system", "content": _system_prompt()}, {"role": "user", "content": user}]


async def _ask(llm: Any, messages: list[dict]) -> Any:
    result = llm.chat_json(
        messages=messages, temperature=TEMPERATURE, timeout=TIMEOUT_S, max_retries=MAX_RETRIES,
    )
    if inspect.isawaitable(result):
        result = await result
    return result


def _shape_content(raw_steps: list, raw_objections: Any, reason: Any, folded_source: str) -> dict:
    """The rules every path applies to what the model wrote for ONE playbook: clip (never
    reject), drop an example the source does not contain, at most MAX_AI_STEPS steps
    (more -> "grouped"), seven objection categories once each. -> {steps, objections,
    reason: None | "grouped"}. Shared by the per-type and the whole-company flows."""
    reason = "grouped" if reason == "grouped" else None
    steps: list[dict] = []
    for raw in raw_steps:
        if not isinstance(raw, dict):
            continue
        label = clip_text(raw.get("label"), MAX_LABEL)
        if not label:
            continue
        step = {"label": label, "criterion": clip_text(raw.get("criterion"), MAX_CRITERION)}
        example = " ".join(str(raw.get("example") or "").split())
        if example and _literal_in(example, folded_source):
            step["example"] = clip_text(example, MAX_EXAMPLE)
        steps.append(step)
    if len(steps) > MAX_AI_STEPS:
        steps = steps[:MAX_AI_STEPS]
        reason = "grouped"

    objections: list[dict] = []
    seen: set[str] = set()
    for raw in raw_objections if isinstance(raw_objections, list) else []:
        if not isinstance(raw, dict):
            continue
        category = str(raw.get("category") or "").strip().lower()
        guidance = clip_text(raw.get("guidance"), MAX_GUIDANCE)
        if category not in OBJECTION_CATEGORIES or not guidance or category in seen:
            continue
        seen.add(category)
        objections.append({"category": category, "guidance": guidance})
    return {"steps": steps, "objections": objections, "reason": reason}


def _shape(data: Any, folded_source: str) -> dict:
    """The model's JSON as clipped, de-duplicated raw steps and objections. Raises
    ValueError when there is nothing usable (not an object, no steps and no
    "no_process")."""
    if not isinstance(data, dict):
        raise ValueError("model output is not an object")
    raw_steps = data.get("steps")
    if raw_steps is None:
        raw_steps = []
    if not isinstance(raw_steps, list):
        raise ValueError("steps is not a list")
    said = data.get("reason") if data.get("reason") in ("no_process", "grouped") else None
    content = _shape_content(raw_steps, data.get("objections"), said, folded_source)
    if not content["steps"]:
        if said != "no_process":
            raise ValueError("model returned no steps")
        return {"steps": [], "objections": [], "reason": "no_process"}
    return content  # steps found: trusted over a "no_process" label


def _generic_indexes(steps: list[dict]) -> list[int]:
    return [i for i, step in enumerate(steps) if generic_criterion(step.get("criterion", ""))]


def _retry_message(lines: list[str]) -> str:
    return (
        "These criteria describe an attitude, not something observable in a transcript:\n"
        + "\n".join(lines)
        + "\nReturn the full JSON again. Rewrite those criteria as what the salesperson says or "
        "what the prospect says or agrees to, using only what the source supports. Keep every "
        "other step exactly as it was."
    )


def _retry_lines(steps: list[dict], indexes: list[int], prefix: str = "") -> list[str]:
    lines = []
    for i in indexes:
        found = ", ".join(f'"{phrase}"' for phrase in generic_phrases(steps[i]["criterion"]))
        lines.append(f'- {prefix}step {i + 1} ("{steps[i]["label"]}"): {found}')
    return lines


def _retry_note(steps: list[dict], indexes: list[int]) -> str:
    return _retry_message(_retry_lines(steps, indexes))


def _finish(shaped: dict, *, fallback: bool, short: bool) -> dict:
    """Normalize (the shape every save uses) and apply the reason rules."""
    steps = normalize_steps(shaped["steps"]) if shaped["steps"] else []
    entries = normalize_objections(shaped["objections"])
    reason = shaped["reason"]
    if short and reason is None:
        reason = "too_short"
    return {
        "steps": steps,
        "objections": [{"category": e["category"], "guidance": e["guidance"]} for e in entries],
        "reason": reason,
        "fallback": fallback,
    }


def _line_fallback(source: str, *, short: bool, fallback: bool) -> dict:
    """The deterministic parser's steps. Same clipping as the model path, so they save."""
    raw = [
        {"label": clip_text(s["label"], MAX_LABEL), "criterion": clip_text(s["criterion"], MAX_CRITERION)}
        for s in parse_playbook_text(source)
    ]
    raw = [s for s in raw if s["label"]]
    if not raw:
        return {"steps": [], "objections": [], "reason": "no_process", "fallback": fallback}
    return _finish({"steps": raw, "objections": [], "reason": None}, fallback=fallback, short=short)


def _client(llm: Any) -> Any:
    client = llm if llm is not None else _llm
    if client is None:
        from app.services.llm import LLMClient

        client = LLMClient()
    return client


async def _ask_with_retry(client: Any, messages: list[dict], shape, generic_of, note_of, usable) -> Any:
    """The model call every path shares: ask, shape, and ask ONCE more (the whole call, with
    a note naming the attitude criteria) when any criterion is generic. At most two calls,
    each bounded by TIMEOUT_S. A first call that fails raises; a failing retry keeps the
    first answer. `shape` may raise ValueError for an unusable answer."""
    first_raw = await asyncio.wait_for(_ask(client, messages), TIMEOUT_S + 5)
    shaped = shape(first_raw)
    if generic_of(shaped):
        try:
            retry_messages = messages + [
                {"role": "assistant", "content": json.dumps(first_raw, ensure_ascii=False)},
                {"role": "user", "content": note_of(shaped)},
            ]
            second = shape(await asyncio.wait_for(_ask(client, retry_messages), TIMEOUT_S + 5))
            if usable(second):
                shaped = second
        except Exception as exc:  # the first answer is still usable
            logger.warning("playbook structure retry failed: %s", type(exc).__name__)
    return shaped


async def structure_source(text: str, motion_key: str, lang: str, *, llm: Any = None) -> dict:
    """{steps, objections, reason, fallback} for one source. `reason`: None, "no_process"
    (the source has no process), "too_short" (too little to be one; the steps are what it
    supports) or "grouped" (more than MAX_AI_STEPS stages were kept as MAX_AI_STEPS).
    `fallback` is true when the steps come from the line parser instead of the model.
    Never raises."""
    source = (text or "").strip()
    lang = "en" if (lang or "").lower().startswith("en") else "es"
    if not _letters(source):
        return {"steps": [], "objections": [], "reason": "too_short", "fallback": False}
    short = _letters(source) < MIN_SOURCE_CHARS
    folded_source = _fold(source[:MAX_SOURCE_CHARS])

    try:
        shaped = await _ask_with_retry(
            _client(llm),
            _messages(source, motion_key, lang),
            lambda raw: _shape(raw, folded_source),
            lambda s: _generic_indexes(s["steps"]),
            lambda s: _retry_note(s["steps"], _generic_indexes(s["steps"])),
            lambda s: bool(s["steps"]),
        )
        generic = _generic_indexes(shaped["steps"])

        if not shaped["steps"]:  # no_process
            if short:
                return _line_fallback(source, short=True, fallback=False)
            return {"steps": [], "objections": [], "reason": "no_process", "fallback": False}

        result = _finish(shaped, fallback=False, short=short)
        for index in generic:
            # Still an attitude after asking twice: keep the step, leave the criterion for a
            # person to write (normalize_steps would have copied the label into it).
            result["steps"][index]["criterion"] = ""
        return result
    except Exception as exc:  # model error, timeout, bad JSON, nothing usable: never blocks
        logger.warning("playbook structure fell back to the line parser: %s", type(exc).__name__)
        return _line_fallback(source, short=short, fallback=True)


# --- the whole company's document: which call types does it cover? ---------------------------

SPLIT_PROMPT_VERSION = "playbook_split_v1"
_SPLIT_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / f"{SPLIT_PROMPT_VERSION}.md"


@lru_cache(maxsize=1)
def _split_prompt() -> str:
    return _SPLIT_PROMPT_PATH.read_text(encoding="utf-8")


def _split_messages(source: str, candidates: list[dict], lang: str) -> list[dict]:
    listing = "\n".join(
        f"- key: {c['key']} | name: {c['label']} | {c.get('description') or 'no description'}" for c in candidates
    )
    user = (
        f"Company language: {'English' if lang == 'en' else 'Spanish'}\n\n"
        f"Candidate call types (use only these keys):\n{listing}\n\n"
        f'Source:\n"""\n{source[:MAX_SOURCE_CHARS]}\n"""'
    )
    return [{"role": "system", "content": _split_prompt()}, {"role": "user", "content": user}]


def _shape_split(data: Any, allowed: set[str], folded_source: str) -> dict:
    """The model's `{"types": [...]}` as clipped raw content per candidate type (first entry
    wins per key; a key that is not a candidate, or a type with no steps, is dropped).
    `{"types": []}` is valid: the source has no process. Raises ValueError when the answer
    is not usable at all (not an object, no list, only unknown keys)."""
    if not isinstance(data, dict):
        raise ValueError("model output is not an object")
    raw_types = data.get("types")
    if raw_types is None and data.get("reason") == "no_process":
        raw_types = []
    if not isinstance(raw_types, list):
        raise ValueError("types is not a list")
    out: list[dict] = []
    seen: set[str] = set()
    unknown = 0
    for raw in raw_types:
        key = str(raw.get("key") or "").strip() if isinstance(raw, dict) else ""
        if key not in allowed:
            unknown += 1
            continue
        raw_steps = raw.get("steps")
        if key in seen or not isinstance(raw_steps, list):
            continue
        content = _shape_content(raw_steps, raw.get("objections"), raw.get("reason"), folded_source)
        if not content["steps"]:
            continue
        seen.add(key)
        out.append({"key": key, **content})
    if raw_types and not out and unknown:
        raise ValueError("model named no candidate type")
    return {"types": out}


def _split_generic(shaped: dict) -> dict[str, list[int]]:
    found = {item["key"]: _generic_indexes(item["steps"]) for item in shaped["types"]}
    return {key: indexes for key, indexes in found.items() if indexes}


def _split_note(shaped: dict) -> str:
    lines: list[str] = []
    for item in shaped["types"]:
        indexes = _generic_indexes(item["steps"])
        lines += _retry_lines(item["steps"], indexes, prefix=f'type "{item["key"]}", ')
    return _retry_message(lines)


async def split_source(text: str, candidates: list[dict], lang: str, *, llm: Any = None) -> dict:
    """One model call for a whole company's document. `candidates` is [{key, label,
    description?}]. -> {types: [{key, reason, steps, objections}], reason: None | "no_process",
    fallback: bool}; each type went through the same rules as structure_source (clip, at most
    MAX_AI_STEPS steps and "grouped", literal examples, one retry when a criterion is an
    attitude then blank it, normalize), so it always saves. `fallback` is true when the model
    failed or returned nothing usable: no type is guessed, the caller asks the manager which
    call type the source is. Never raises."""
    source = (text or "").strip()
    lang = "en" if (lang or "").lower().startswith("en") else "es"
    if not _letters(source) or not candidates:
        return {"types": [], "reason": "no_process", "fallback": False}
    short = _letters(source) < MIN_SOURCE_CHARS
    folded_source = _fold(source[:MAX_SOURCE_CHARS])
    allowed = {c["key"] for c in candidates}
    try:
        shaped = await _ask_with_retry(
            _client(llm),
            _split_messages(source, candidates, lang),
            lambda raw: _shape_split(raw, allowed, folded_source),
            _split_generic,
            _split_note,
            lambda s: bool(s["types"]),
        )
        if not shaped["types"]:
            if short:  # too little to tell what it is: let the manager pick the call type
                return {"types": [], "reason": None, "fallback": True}
            return {"types": [], "reason": "no_process", "fallback": False}
        types = []
        for item in shaped["types"]:
            generic = _generic_indexes(item["steps"])
            result = _finish(item, fallback=False, short=short)
            for index in generic:
                result["steps"][index]["criterion"] = ""
            types.append({
                "key": item["key"],
                "reason": result["reason"],
                "steps": result["steps"],
                "objections": result["objections"],
            })
        return {"types": types, "reason": None, "fallback": False}
    except Exception as exc:  # model error, timeout, bad JSON: never a 500, never a guessed type
        logger.warning("playbook split failed, asking for the call type: %s", type(exc).__name__)
        return {"types": [], "reason": None, "fallback": True}
