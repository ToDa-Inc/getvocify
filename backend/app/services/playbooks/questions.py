"""Product questions in a company's material: «¿Se integra con Salesforce?», «¿Dónde se guardan los datos?».

A document the Head of Sales hands over (a product sheet, an FAQ, a security note) often answers questions a
prospect asks on a call. Live help already knows how to answer the team's own objections (category `custom`: a
label, how the prospect says it, the approved answer), so a question and its answer are saved the same way and
nothing about live help changes.

One model call, then deterministic rules (the model is never trusted with a limit or a fact):
- a question stays only if the document literally contains the quote the model points to, so an answer nobody wrote
  is dropped;
- label, trigger and answer are clipped to the limits the editor saves with; a question with no label or no answer
  is dropped, and so is a second one with the same label;
- at most MAX_QUESTIONS, and a model that fails or answers something unusable gives an empty list, never an error:
  structuring a document never depends on this step.
"""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.services.playbooks.structure import MAX_SOURCE_CHARS, _ask, _client, _fold, _literal_in, _text, timeout_for
from app.services.playbooks.structured import (
    CUSTOM_CATEGORY,
    MAX_CUSTOM_OBJECTIONS,
    MAX_GUIDANCE,
    MAX_OBJECTION_LABEL,
    MAX_TRIGGER,
)

logger = logging.getLogger(__name__)

PROMPT_VERSION = "playbook_questions_v1"
_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / f"{PROMPT_VERSION}.md"
MAX_QUESTIONS = MAX_CUSTOM_OBJECTIONS


@lru_cache(maxsize=1)
def _prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def shape_questions(raw: Any, folded_source: str) -> list[dict]:
    """The model's `{"questions": [...]}` as custom objection entries, with the rules above applied."""
    items = raw.get("questions") if isinstance(raw, dict) else None
    out: list[dict] = []
    seen: set[str] = set()
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        label = _text(item, "label", MAX_OBJECTION_LABEL)
        answer = _text(item, "answer", MAX_GUIDANCE)
        if not label or not answer or label.casefold() in seen:
            continue
        if not _literal_in(str(item.get("quote") or ""), folded_source):
            continue
        seen.add(label.casefold())
        out.append({
            "category": CUSTOM_CATEGORY, "label": label,
            "trigger": _text(item, "trigger", MAX_TRIGGER), "guidance": answer,
        })
        if len(out) >= MAX_QUESTIONS:
            break
    return out


async def extract_questions(text: str, lang: str, *, llm: Any = None) -> list[dict]:
    """The product questions `text` answers, as custom objection entries. [] on any failure."""
    source = (text or "").strip()[:MAX_SOURCE_CHARS]
    if not source:
        return []
    user = f"Company language: {'English' if lang == 'en' else 'Spanish'}\n\nSource:\n\"\"\"\n{source}\n\"\"\""
    messages = [{"role": "system", "content": _prompt()}, {"role": "user", "content": user}]
    timeout = timeout_for(source)
    try:
        raw = await asyncio.wait_for(_ask(_client(llm), messages, timeout), timeout + 5)
    except Exception as exc:  # structuring a document never depends on this step
        logger.warning("product questions not extracted: %s", type(exc).__name__)
        return []
    return shape_questions(raw, _fold(source))


def add_questions(objections: list[dict], questions: list[dict]) -> list[dict]:
    """`objections` plus the questions whose label it does not have yet. An answer the Head of Sales already has
    is never overwritten, and the company's own objections stay within MAX_CUSTOM_OBJECTIONS."""
    out = [dict(item) for item in objections]
    labels = {str(item.get("label") or "").strip().casefold() for item in out if item.get("category") == CUSTOM_CATEGORY}
    customs = sum(1 for item in out if item.get("category") == CUSTOM_CATEGORY)
    for question in questions:
        label = str(question.get("label") or "").strip().casefold()
        if not label or label in labels or customs >= MAX_CUSTOM_OBJECTIONS:
            continue
        labels.add(label)
        customs += 1
        out.append(dict(question))
    return out
