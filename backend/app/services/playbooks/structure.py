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
- three layers (playbook_structure_v2 / playbook_split_v2): besides steps and objection answers the
  model returns the objections the company names that fit no fixed category (`custom`), the
  qualification criteria ("what has to come out of the call") and, for a whole-company document,
  what it says about the company. All of it is clipped like the steps, and what the source does
  not say stays empty: a competitor whose name is not in the source, or a number that is not in
  it, is dropped;
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
import time
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.services.playbooks.catalog import QUALIFICATION_TEMPLATE_KEYS, qualification_criteria
from app.services.playbooks.knowledge import normalize_knowledge
from app.services.playbooks.motion import goal_for
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
    MAX_TRIGGER,
    OBJECTION_CATEGORIES,
    clip_text,
    normalize_objections,
    normalize_qualification,
    normalize_steps,
    objection_view,
    parse_playbook_text,
    strip_markdown,
)
from app.services.text_guard import generic_criterion, generic_phrases

logger = logging.getLogger(__name__)

PROMPT_VERSION = "playbook_structure_v2"
_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / f"{PROMPT_VERSION}.md"

MAX_AI_STEPS = 7
# One attempt at the client. The Head of Sales waits on this call, so a slow model becomes
# the line parser, not an endless spinner; but a whole playbook document takes the model
# longer than a paragraph, and a rushed timeout turned good documents into the parser's
# rougher steps. Short sources get TIMEOUT_S, long ones up to LONG_TIMEOUT_S.
TIMEOUT_S = 25.0
LONG_TIMEOUT_S = 60.0
LONG_SOURCE_CHARS = 2_500

# The whole company's document writes every call type and the company block in ONE answer:
# a real playbook (4 types, ~20 steps, objections, criteria) takes the model well over 25 s,
# and fell back to "¿Para qué llamada es?" every time. The screen waits 120 s for this call
# (src/features/playbooks/api.ts), so the split gets 85 s and the whole call stays under 110 s:
# the attitude retry only runs when there is still time for it.
SPLIT_TIMEOUT_S = 85.0
SPLIT_BUDGET_S = 110.0
_clock = time.monotonic
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


def _templates_block(lang: str) -> str:
    """The qualification frameworks the source may name, as criteria in the source's language.
    Kept out of the prompt file so they have one home (catalog.py); the model uses one only when
    the source names it."""
    lines = [
        f"{key.upper()}: {json.dumps(qualification_criteria(key, lang), ensure_ascii=False)}"
        for key in QUALIFICATION_TEMPLATE_KEYS
    ]
    return "Qualification templates (use one ONLY when the source names that framework):\n" + "\n".join(lines)


def _messages(source: str, motion_key: str, lang: str) -> list[dict]:
    body = source[:MAX_SOURCE_CHARS]
    user = (
        f"Call type: {call_type_label(motion_key, lang)} (key: {motion_key})\n"
        f"Goal: {goal_label(motion_key, lang)}\n"
        f"Company language: {'English' if lang == 'en' else 'Spanish'}\n\n"
        f"{_templates_block(lang)}\n\n"
        f'Source:\n"""\n{body}\n"""'
    )
    return [{"role": "system", "content": _system_prompt()}, {"role": "user", "content": user}]


def timeout_for(source: str) -> float:
    return LONG_TIMEOUT_S if len(source) >= LONG_SOURCE_CHARS else TIMEOUT_S


async def _ask(llm: Any, messages: list[dict], timeout: float = TIMEOUT_S) -> Any:
    result = llm.chat_json(
        messages=messages, temperature=TEMPERATURE, timeout=timeout, max_retries=MAX_RETRIES,
    )
    if inspect.isawaitable(result):
        result = await result
    return result


def _text(raw: dict, name: str, limit: int) -> str:
    """One field the model wrote, clipped, without the markdown it copied from the source."""
    return clip_text(strip_markdown(raw.get(name)), limit)


def _shape_objections(raw_objections: Any) -> list[dict]:
    """The model's objections as clipped entries: one per fixed category (an answer is
    required), `custom` ones need a label (their answer may be empty), at most
    MAX_CUSTOM_OBJECTIONS, none twice by label. Anything else the prompt returns (meaning /
    question / proof) is not kept."""
    out: list[dict] = []
    seen: set[str] = set()
    custom_labels: set[str] = set()
    customs = 0
    for raw in raw_objections if isinstance(raw_objections, list) else []:
        if not isinstance(raw, dict):
            continue
        category = str(raw.get("category") or "").strip().lower()
        guidance = _text(raw, "guidance", MAX_GUIDANCE)
        if category == CUSTOM_CATEGORY:
            label = _text(raw, "label", MAX_OBJECTION_LABEL)
            if not label or label.casefold() in custom_labels or customs >= MAX_CUSTOM_OBJECTIONS:
                continue
            custom_labels.add(label.casefold())
            customs += 1
            entry = {
                "category": category, "label": label,
                "trigger": _text(raw, "trigger", MAX_TRIGGER), "guidance": guidance,
            }
        elif category in OBJECTION_CATEGORIES and guidance and category not in seen:
            seen.add(category)
            entry = {"category": category, "guidance": guidance}
        else:
            continue
        out.append(entry)
    return out


def _shape_qualification(raw_criteria: Any) -> list[dict]:
    """The model's criteria as clipped ones: a label each, at most MAX_CRITERIA, none twice by
    label. `criterion_id` is kept when the model reused a template's."""
    out: list[dict] = []
    seen: set[str] = set()
    for raw in raw_criteria if isinstance(raw_criteria, list) else []:
        if not isinstance(raw, dict):
            continue
        label = _text(raw, "label", MAX_CRITERION_LABEL)
        if not label or label.casefold() in seen:
            continue
        seen.add(label.casefold())
        item = {"label": label}
        if raw.get("criterion_id"):
            item["criterion_id"] = str(raw["criterion_id"]).strip()
        value = _text(raw, "good", MAX_CRITERION_TEXT)
        if value:
            item["good"] = value
        out.append(item)
        if len(out) >= MAX_CRITERIA:
            break
    return out


def _shape_content(
    raw_steps: list, raw_objections: Any, reason: Any, folded_source: str, raw_qualification: Any = None,
) -> dict:
    """The rules every path applies to what the model wrote for ONE playbook: clip (never
    reject), drop an example the source does not contain, at most MAX_AI_STEPS steps
    (more -> "grouped"), objections once per fixed category plus the company's own, criteria
    clipped. -> {steps, objections, qualification, reason: None | "grouped"}. Shared by the
    per-type and the whole-company flows."""
    reason = "grouped" if reason == "grouped" else None
    steps: list[dict] = []
    for raw in raw_steps:
        if not isinstance(raw, dict):
            continue
        label = _text(raw, "label", MAX_LABEL)
        if not label:
            continue
        step = {"label": label, "criterion": _text(raw, "criterion", MAX_CRITERION)}
        example = " ".join(str(raw.get("example") or "").split())
        if example and _literal_in(example, folded_source):
            step["example"] = clip_text(example, MAX_EXAMPLE)
        steps.append(step)
    if len(steps) > MAX_AI_STEPS:
        steps = steps[:MAX_AI_STEPS]
        reason = "grouped"
    return {
        "steps": steps,
        "objections": _shape_objections(raw_objections),
        "qualification": _shape_qualification(raw_qualification),
        "reason": reason,
    }


def _deaccent(folded: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", folded) if not unicodedata.combining(ch))


_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def _digits(text: str) -> set[str]:
    return {re.sub(r"[.,]", "", run) for run in _NUMBER.findall(text or "")}


def _shape_company(raw: Any, folded_source: str, raw_source: str | None = None) -> dict:
    """What the model says about the company, in the stored shape (normalize_knowledge clips and
    caps it). Two guards against invention: a competitor whose name the source never mentions is
    dropped, and a customer case whose result gives a figure the source does not contain loses it."""
    data = normalize_knowledge(raw)
    plain = _deaccent(folded_source)
    source_digits = _digits(raw_source if raw_source is not None else folded_source)
    data["competitors"] = [item for item in data["competitors"] if _deaccent(_fold(item["name"])) in plain]
    data["proofs"] = [
        proof if _digits(proof["change"]) <= source_digits else {**proof, "change": ""} for proof in data["proofs"]
    ]
    return data


def _shape(data: Any, folded_source: str) -> dict:
    """The model's JSON as clipped, de-duplicated raw steps, objections and criteria. Raises
    ValueError when there is nothing usable (not an object, no steps and no
    "no_process"). A source with criteria or the company's own objections but no steps is
    "no_process" that still carries them."""
    if not isinstance(data, dict):
        raise ValueError("model output is not an object")
    raw_steps = data.get("steps")
    if raw_steps is None:
        raw_steps = []
    if not isinstance(raw_steps, list):
        raise ValueError("steps is not a list")
    said = data.get("reason") if data.get("reason") in ("no_process", "grouped") else None
    content = _shape_content(raw_steps, data.get("objections"), said, folded_source, data.get("qualification"))
    if not content["steps"]:
        if said != "no_process" and not content["qualification"] and not content["objections"]:
            raise ValueError("model returned no steps")
        return {**content, "reason": "no_process"}
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
        "objections": [objection_view(e) for e in entries],
        "qualification": normalize_qualification(shaped.get("qualification")),
        "reason": reason,
        "fallback": fallback,
    }


def failure_of(exc: BaseException) -> dict:
    """Why the model path failed, for the person who is waiting: {kind, detail}. kind is
    "timeout", "invalid_answer" (not the JSON asked for) or "model_error" (the provider said
    no: key, model, quota). detail is the provider's own message, short; it never carries the key."""
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        kind = "timeout"
    elif isinstance(exc, (ValueError, json.JSONDecodeError, KeyError, TypeError)):
        kind = "invalid_answer"
    else:
        kind = "model_error"
    detail = " ".join(str(exc).split())[:200]
    return {"kind": kind, "detail": f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__}


def _line_fallback(source: str, *, short: bool, fallback: bool) -> dict:
    """The deterministic parser's steps. Same clipping as the model path, so they save."""
    raw = [
        {"label": clip_text(s["label"], MAX_LABEL), "criterion": clip_text(s["criterion"], MAX_CRITERION)}
        for s in parse_playbook_text(source)
    ]
    raw = [s for s in raw if s["label"]]
    if not raw:
        return {"steps": [], "objections": [], "qualification": [], "reason": "no_process", "fallback": fallback}
    return _finish({"steps": raw, "objections": [], "qualification": [], "reason": None}, fallback=fallback, short=short)


def _client(llm: Any) -> Any:
    client = llm if llm is not None else _llm
    if client is None:
        from app.services.llm import LLMClient

        client = LLMClient()
    return client


async def _ask_with_retry(
    client: Any, messages: list[dict], shape, generic_of, note_of, usable,
    *, timeout: float = TIMEOUT_S, budget: float | None = None,
) -> Any:
    """The model call every path shares: ask, shape, and ask ONCE more (the whole call, with
    a note naming the attitude criteria) when any criterion is generic. At most two calls,
    each bounded by `timeout`; with a `budget`, the retry only runs if a whole call still fits
    in it. A first call that fails raises; a failing retry keeps the first answer. `shape`
    may raise ValueError for an unusable answer."""
    started = _clock()
    first_raw = await asyncio.wait_for(_ask(client, messages, timeout), timeout + 5)
    shaped = shape(first_raw)
    out_of_time = budget is not None and _clock() - started + timeout > budget
    if generic_of(shaped) and not out_of_time:
        try:
            retry_messages = messages + [
                {"role": "assistant", "content": json.dumps(first_raw, ensure_ascii=False)},
                {"role": "user", "content": note_of(shaped)},
            ]
            second = shape(await asyncio.wait_for(_ask(client, retry_messages, timeout), timeout + 5))
            if usable(second):
                shaped = second
        except Exception as exc:  # the first answer is still usable
            logger.warning("playbook structure retry failed: %s", type(exc).__name__)
    return shaped


async def structure_source(text: str, motion_key: str, lang: str, *, llm: Any = None) -> dict:
    """{steps, objections, qualification, reason, fallback} for one source. `reason`: None, "no_process"
    (the source has no process), "too_short" (too little to be one; the steps are what it
    supports) or "grouped" (more than MAX_AI_STEPS stages were kept as MAX_AI_STEPS).
    `fallback` is true when the steps come from the line parser instead of the model.
    Never raises."""
    source = (text or "").strip()
    lang = "en" if (lang or "").lower().startswith("en") else "es"
    if not _letters(source):
        return {"steps": [], "objections": [], "qualification": [], "reason": "too_short", "fallback": False}
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
            timeout=timeout_for(source),
        )
        generic = _generic_indexes(shaped["steps"])

        if not shaped["steps"]:  # no_process (it may still carry criteria and the company's own objections)
            if short:
                return _line_fallback(source, short=True, fallback=False)
            result = _finish(shaped, fallback=False, short=False)
            return {**result, "reason": "no_process"}

        result = _finish(shaped, fallback=False, short=short)
        for index in generic:
            # Still an attitude after asking twice: keep the step, leave the criterion for a
            # person to write (normalize_steps would have copied the label into it).
            result["steps"][index]["criterion"] = ""
        return result
    except Exception as exc:  # model error, timeout, bad JSON, nothing usable: never blocks
        logger.warning("playbook structure fell back to the line parser: %s: %s", type(exc).__name__, exc)
        return {**_line_fallback(source, short=short, fallback=True), "error": failure_of(exc)}


# --- the whole company's document: which call types does it cover? ---------------------------

SPLIT_PROMPT_VERSION = "playbook_split_v2"
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
        f"{_templates_block(lang)}\n\n"
        f'Source:\n"""\n{source[:MAX_SOURCE_CHARS]}\n"""'
    )
    return [{"role": "system", "content": _split_prompt()}, {"role": "user", "content": user}]


def _shape_split(data: Any, allowed: set[str], folded_source: str, raw_source: str | None = None) -> dict:
    """The model's `{"types": [...], "company": {...}}` as clipped raw content per candidate type
    (first entry wins per key; a key that is not a candidate, or a type with no steps, is
    dropped) and the company block in its stored shape. `{"types": []}` is valid: the source
    has no process (it may still say things about the company). Raises ValueError when the
    answer is not usable at all (not an object, no list, only unknown keys)."""
    if not isinstance(data, dict):
        raise ValueError("model output is not an object")
    raw_types = data.get("types")
    if raw_types is None and (data.get("reason") == "no_process" or isinstance(data.get("company"), dict)):
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
        content = _shape_content(
            raw_steps, raw.get("objections"), raw.get("reason"), folded_source, raw.get("qualification"),
        )
        if not content["steps"]:
            continue
        seen.add(key)
        out.append({"key": key, **content})
    if raw_types and not out and unknown:
        raise ValueError("model named no candidate type")
    return {"types": out, "company": _shape_company(data.get("company"), folded_source, raw_source)}


def _split_generic(shaped: dict) -> dict[str, list[int]]:
    found = {item["key"]: _generic_indexes(item["steps"]) for item in shaped["types"]}
    return {key: indexes for key, indexes in found.items() if indexes}


def _split_note(shaped: dict) -> str:
    lines: list[str] = []
    for item in shaped["types"]:
        indexes = _generic_indexes(item["steps"])
        lines += _retry_lines(item["steps"], indexes, prefix=f'type "{item["key"]}", ')
    return _retry_message(lines)


# --- a document that already says which section is which call type ---------------------------

_HEADING = re.compile(r"^\s{0,3}(#{1,3})\s+(.+?)\s*#*\s*$")
# Words in a section title, in the order they decide (a "Discovery (se puede combinar con la
# Demo)" title is a discovery). Each maps to catalog keys, best first; the first one that is a
# candidate wins (routing off only has `discovery` and `closing`).
_TITLE_RULES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("inbound",), ("inbound", "discovery")),
    (("frio", "cold call", "cold-call", "prospeccion", "captacion"), ("discovery",)),
    (("propuesta", "proposal", "negociacion", "negotiation", "decision"), ("negotiation", "closing")),
    (("discovery", "descubrimiento"), ("ae_discovery", "closing")),
    (("demo", "cierre", "closing"), ("closing",)),
)


def _title_key(title: str, allowed: set[str]) -> str | None:
    """The candidate a section title names, or None. A title that only names the role (SDR or
    AE) falls back to that role's first type."""
    folded = _fold(unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode())
    words = set(folded.split())
    is_sdr, is_ae = "sdr" in words, "ae" in words or "closer" in words
    for needles, keys in _TITLE_RULES:
        if any(needle in folded for needle in needles):
            if needles[0] == "discovery" and is_sdr and not is_ae:
                keys = ("discovery",)  # an SDR's "discovery" call is their cold call
            for key in keys:
                if key in allowed:
                    return key
    if is_sdr and "discovery" in allowed:
        return "discovery"
    if is_ae and "closing" in allowed:
        return "closing"
    return None


def titled_sections(text: str, allowed: set[str]) -> tuple[list[tuple[str, str]], str] | None:
    """([(key, section text)], everything else) when the document's own titles name at least
    two call types, else None. The level of the first typed title is the section level; the
    text under a title of that level that names no type (the company, the funnel) and the text
    before the first section go to "everything else". Two sections for one key are merged."""
    lines = text.splitlines()
    heads: list[tuple[int, int, str | None]] = []  # (line, level, key)
    for index, line in enumerate(lines):
        match = _HEADING.match(line)
        if match:
            heads.append((index, len(match.group(1)), _title_key(match.group(2), allowed)))
    typed = [head for head in heads if head[2]]
    if len({head[2] for head in typed}) < 2:
        return None
    level = min(head[1] for head in typed)
    cuts = [head for head in heads if head[1] <= level]
    order: list[str] = []
    by_key: dict[str, list[str]] = {}
    rest: list[str] = ["\n".join(lines[: cuts[0][0]])]
    for position, (start, _level, key) in enumerate(cuts):
        end = cuts[position + 1][0] if position + 1 < len(cuts) else len(lines)
        chunk = "\n".join(lines[start:end]).strip()
        if key:
            if key not in by_key:
                order.append(key)
            by_key.setdefault(key, []).append(chunk)
        else:
            rest.append(chunk)
    return [(key, "\n\n".join(by_key[key])) for key in order], "\n\n".join(p for p in rest if p.strip())


async def _split_by_titles(
    sections: list[tuple[str, str]], rest: str, candidates: list[dict], lang: str, llm: Any,
) -> dict:
    """Each titled section through structure_source (one short answer each, in parallel) and
    the rest through the company split, which only has the company to write. Same result
    shape as split_source; `fallback` only when no section got steps from the model."""
    client = _client(llm)
    calls = [structure_source(body, key, lang, llm=client) for key, body in sections]
    with_company = _letters(rest) >= MIN_SOURCE_CHARS
    if with_company:
        calls.append(split_source(rest, candidates, lang, llm=client, by_titles=False))
    answers = await asyncio.gather(*calls)
    results = answers[: len(sections)]
    company = answers[-1]["company"] if with_company else normalize_knowledge({})
    types = [
        {
            "key": key,
            "reason": result["reason"],
            "steps": result["steps"],
            "objections": result["objections"],
            "qualification": result["qualification"],
        }
        for (key, _body), result in zip(sections, results)
        if result["steps"] and not result.get("fallback")
    ]
    if not types:
        error = next((result["error"] for result in results if result.get("error")), None)
        return {"types": [], "company": normalize_knowledge({}), "reason": None, "fallback": True, "error": error}
    return {"types": types, "company": company, "reason": None, "fallback": False}


async def split_source(text: str, candidates: list[dict], lang: str, *, llm: Any = None, by_titles: bool = True) -> dict:
    """One model call for a whole company's document. `candidates` is [{key, label,
    description?}]. -> {types: [{key, reason, steps, objections, qualification}], company:
    knowledge shape (empty when the source says nothing about the company), reason: None |
    "no_process", fallback: bool}; each type went through the same rules as structure_source (clip, at most
    MAX_AI_STEPS steps and "grouped", literal examples, one retry when a criterion is an
    attitude then blank it, normalize), so it always saves. `fallback` is true when the model
    failed or returned nothing usable: no type is guessed, the caller asks the manager which
    call type the source is. Never raises."""
    source = (text or "").strip()
    lang = "en" if (lang or "").lower().startswith("en") else "es"
    empty_company = normalize_knowledge({})
    if not _letters(source) or not candidates:
        return {"types": [], "company": empty_company, "reason": "no_process", "fallback": False}
    short = _letters(source) < MIN_SOURCE_CHARS
    folded_source = _fold(source[:MAX_SOURCE_CHARS])
    allowed = {c["key"] for c in candidates}
    # The document already names its call types in its titles: split there, not with one huge
    # answer that has to write every type at once (it does not fit in the time the screen waits).
    titled = titled_sections(source[:MAX_SOURCE_CHARS], allowed) if by_titles else None
    if titled:
        try:
            return await _split_by_titles(titled[0], titled[1], candidates, lang, llm)
        except Exception as exc:  # never a 500: fall through to the one-answer split
            logger.warning("playbook split by titles failed: %s", type(exc).__name__)
    try:
        shaped = await _ask_with_retry(
            _client(llm),
            _split_messages(source, candidates, lang),
            lambda raw: _shape_split(raw, allowed, folded_source, source[:MAX_SOURCE_CHARS]),
            _split_generic,
            _split_note,
            lambda s: bool(s["types"]),
            timeout=SPLIT_TIMEOUT_S,
            budget=SPLIT_BUDGET_S,
        )
        if not shaped["types"]:
            if short:  # too little to tell what it is: let the manager pick the call type
                return {"types": [], "company": empty_company, "reason": None, "fallback": True}
            return {"types": [], "company": shaped["company"], "reason": "no_process", "fallback": False}
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
                "qualification": result["qualification"],
            })
        return {"types": types, "company": shaped["company"], "reason": None, "fallback": False}
    except Exception as exc:  # model error, timeout, bad JSON: never a 500, never a guessed type
        logger.warning("playbook split failed, asking for the call type: %s: %s", type(exc).__name__, exc)
        return {"types": [], "company": empty_company, "reason": None, "fallback": True, "error": failure_of(exc)}
