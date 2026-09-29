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
    reason = data.get("reason") if data.get("reason") in ("no_process", "grouped") else None

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
    raw_objections = data.get("objections")
    for raw in raw_objections if isinstance(raw_objections, list) else []:
        if not isinstance(raw, dict):
            continue
        category = str(raw.get("category") or "").strip().lower()
        guidance = clip_text(raw.get("guidance"), MAX_GUIDANCE)
        if category not in OBJECTION_CATEGORIES or not guidance or category in seen:
            continue
        seen.add(category)
        objections.append({"category": category, "guidance": guidance})

    if not steps:
        if reason != "no_process":
            raise ValueError("model returned no steps")
        return {"steps": [], "objections": [], "reason": "no_process"}
    if reason == "no_process":
        reason = None  # it did find steps: trust them over the label
    return {"steps": steps, "objections": objections, "reason": reason}


def _generic_indexes(steps: list[dict]) -> list[int]:
    return [i for i, step in enumerate(steps) if generic_criterion(step.get("criterion", ""))]


def _retry_note(steps: list[dict], indexes: list[int]) -> str:
    lines = []
    for i in indexes:
        found = ", ".join(f'"{phrase}"' for phrase in generic_phrases(steps[i]["criterion"]))
        lines.append(f'- step {i + 1} ("{steps[i]["label"]}"): {found}')
    return (
        "These criteria describe an attitude, not something observable in a transcript:\n"
        + "\n".join(lines)
        + "\nReturn the full JSON again. Rewrite those criteria as what the salesperson says or "
        "what the prospect says or agrees to, using only what the source supports. Keep every "
        "other step exactly as it was."
    )


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
        client = llm if llm is not None else _llm
        if client is None:
            from app.services.llm import LLMClient

            client = LLMClient()
        messages = _messages(source, motion_key, lang)
        first_raw = await asyncio.wait_for(_ask(client, messages), TIMEOUT_S + 5)
        shaped = _shape(first_raw, folded_source)

        generic = _generic_indexes(shaped["steps"])
        if generic:
            try:
                retry_messages = messages + [
                    {"role": "assistant", "content": json.dumps(first_raw, ensure_ascii=False)},
                    {"role": "user", "content": _retry_note(shaped["steps"], generic)},
                ]
                second = _shape(
                    await asyncio.wait_for(_ask(client, retry_messages), TIMEOUT_S + 5), folded_source,
                )
                if second["steps"]:
                    shaped = second
            except Exception as exc:  # the first answer is still usable
                logger.warning("playbook structure retry failed: %s", type(exc).__name__)
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
