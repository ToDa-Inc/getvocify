"""The trial ("La prueba"): the Head of Sales sees how Vocify would answer what customers say, and corrects it.

Part 3, the verdicts: what the Head of Sales decides about each case, how it changes the draft, the result and the
activation. A verdict never goes past the editor's own limits: an answer that does not fit is refused.

Part 2, running a case: the same turn check and the same card writer live help uses (their functions are CALLED, never
changed), fed with the draft instead of the published playbook, so what the Head of Sales sees is what a rep would see
once the draft is published and nothing is published to find out.

Part 1, the cases. 10 to 12 things a customer might say, never an answer and never a wrong one: first what prospects
really said in live calls (most repeated first, at most 8), then phrases the company's own material suggests (one model
call), then the usual objections up to the minimum, so a company with no calls and no documents still has a trial.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.api.copilot import _matched_entry
from app.services.copilot import turn
from app.services.copilot.grounding import SuggestGrounding
from app.services.copilot.playbook_objections import custom_entries
from app.services.copilot.prompts import today_line
from app.services.copilot.suggest import stream_objection_suggestion
from app.services.copilot.turn import read_turn
from app.services.playbooks.model_calls import branch_text
from app.services.playbooks.structure import _ask, _client, _fold, timeout_for
from app.services.playbooks.structured import (
    CUSTOM_CATEGORY,
    MAX_CUSTOM_OBJECTIONS,
    MAX_GUIDANCE,
    MAX_OBJECTION_LABEL,
    MAX_TRIGGER,
    OBJECTION_CATEGORIES,
    clip_text,
    slug,
)
from app.services.playbooks.versions import PublishError

logger = logging.getLogger(__name__)

CASES_PROMPT_VERSION = "playbook_trial_cases_v1"
_CASES_PROMPT = Path(__file__).resolve().parents[2] / "prompts" / f"{CASES_PROMPT_VERSION}.md"
MIN_CASES = 10
MAX_CASES = 12
MAX_REAL = 8
MIN_REAL_CHARS = 20
MAX_CASE_CHARS = 200
MAX_MATERIAL_CHARS = 8000

# (kind of objection or question, what a customer says): the same shapes live help is built for.
TYPICAL_OBJECTIONS: dict[str, list[tuple[str, str]]] = {
    "es": [
        ("price", "Me parece caro para lo que hacéis."),
        ("timing", "Ahora mismo no es buen momento, llamadme el trimestre que viene."),
        ("authority", "Eso lo decide mi director, yo no puedo aprobarlo."),
        ("competitor", "Ya trabajamos con otra herramienta y estamos contentos."),
        ("status_quo", "Nos organizamos bien con un Excel, no veo por qué cambiar."),
        ("trust", "¿Y cómo sé que esto funciona de verdad en un equipo como el nuestro?"),
        ("question", "¿Se integra con nuestro CRM?"),
        ("question", "¿Cuánto cuesta y qué incluye?"),
        ("question", "¿Cuánto se tarda en ponerlo en marcha?"),
        ("timing", "Mándame un email y lo vemos."),
        ("question", "¿Dónde se guardan nuestros datos?"),
        ("price", "Otra empresa me lo ofrece más barato."),
    ],
    "en": [
        ("price", "That looks expensive for what you do."),
        ("timing", "It's not a good moment right now, call me next quarter."),
        ("authority", "My director decides that, I can't approve it."),
        ("competitor", "We already use another tool and we're happy with it."),
        ("status_quo", "We get by fine with a spreadsheet, I don't see why we'd change."),
        ("trust", "How do I know this really works for a team like ours?"),
        ("question", "Does it integrate with our CRM?"),
        ("question", "How much does it cost and what does it include?"),
        ("question", "How long does it take to get started?"),
        ("timing", "Send me an email and we'll look at it."),
        ("question", "Where is our data stored?"),
        ("price", "Another company offers it to me for less."),
    ],
}


@lru_cache(maxsize=1)
def _cases_prompt() -> str:
    return _CASES_PROMPT.read_text(encoding="utf-8")


async def _document_phrases(texts: list[str], lang: str, want: int, llm: Any) -> list[str]:
    """Things a customer could say that the company's own material makes relevant. [] when there is no material or the
    model fails: the trial never depends on this call."""
    material = "\n\n".join(text.strip() for text in texts if text and text.strip())[:MAX_MATERIAL_CHARS]
    if not material or want <= 0:
        return []
    user = (
        f"Company language: {'English' if lang == 'en' else 'Spanish'}\nHow many phrases: {want}\n\n"
        f'Material:\n"""\n{material}\n"""'
    )
    messages = [{"role": "system", "content": _cases_prompt()}, {"role": "user", "content": user}]
    timeout = timeout_for(material)
    try:
        raw = await asyncio.wait_for(_ask(_client(llm), messages, timeout), timeout + 5)
    except Exception as exc:
        logger.warning("trial cases not written from the material: %s", type(exc).__name__)
        return []
    phrases = raw.get("phrases") if isinstance(raw, dict) else None
    return [p for p in phrases if isinstance(p, str)][:want] if isinstance(phrases, list) else []


async def build_cases(
    *, events: list[dict], source_texts: list[str], entries: list[dict], lang: str, motion_key: str,
    limit: int = MAX_CASES, llm: Any = None,
) -> list[dict]:
    """[{id, source: real | document | typical, client_text, motion_key}], at most `limit` (never more than MAX_CASES),
    and at least MIN_CASES when the limit allows. No case holds an answer, so none can be a wrong one."""
    del entries  # the playbook's own answers are never shown as customer phrases
    lang = "en" if str(lang or "").lower().startswith("en") else "es"
    limit = max(1, min(int(limit), MAX_CASES))
    cases: list[dict] = []
    seen: set[str] = set()

    def add(source: str, text: str) -> None:
        phrase = clip_text(" ".join(str(text or "").split()), MAX_CASE_CHARS)
        key = _fold(phrase)
        if not phrase or key in seen or len(cases) >= limit:
            return
        seen.add(key)
        cases.append({
            "id": "c" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:8],
            "source": source, "client_text": phrase, "motion_key": motion_key,
        })

    counts: Counter[str] = Counter()
    first: dict[str, str] = {}
    for event in events:
        phrase = " ".join(str(event.get("latest_turn") or "").split())
        if not event.get("is_objection") or len(phrase) < MIN_REAL_CHARS:
            continue
        key = _fold(phrase)
        counts[key] += 1
        first.setdefault(key, phrase)
    order = {key: index for index, key in enumerate(first)}
    for key in sorted(first, key=lambda k: (-counts[k], order[k]))[:MAX_REAL]:
        add("real", first[key])

    for phrase in await _document_phrases(source_texts, lang, limit - len(cases), llm):
        add("document", phrase)
    target = min(limit, MIN_CASES)
    for _, phrase in TYPICAL_OBJECTIONS[lang]:
        if len(cases) >= target:
            break
        add("typical", phrase)
    return cases


# --- part 2: running a case against the draft ----------------------------------------------------------------

CALL_MODE = "softphone"  # a live call: the mode live help writes its one line for


def draft_snapshot(editor: dict, motion_key: str) -> dict:
    """The draft of a call type as live help reads a published playbook: {sales_motion_key, version_id, steps, entries,
    qualification}. A type with nothing yet is an empty snapshot."""
    version = (editor or {}).get("version") or {}
    return {
        "sales_motion_key": motion_key,
        "version_id": str(version.get("id") or "draft"),
        "steps": list(version.get("steps") or []),
        "entries": list(version.get("entries") or []),
        "qualification": list(version.get("qualification") or []),
    }


async def run_case(case: dict, *, snapshot: dict, knowledge: dict | None, product_context: str, lang: str) -> dict:
    """What live help would show for this customer phrase with `snapshot` as the playbook ->
    {detected, entry_id, label, card: {say_this, source_id, objection_type} | None, grounded}. `detected` is what the turn check
    named ("none" when live help would stay silent, "unknown" when the check could not be reached and the card writer
    is asked directly, as the app does). Same steps as the live endpoint, which a test keeps in step with."""
    del lang  # live help writes in the language of the customer's words
    text = case["client_text"]
    grounding = SuggestGrounding(
        interaction_kind="call", playbook_version_id=snapshot["version_id"], evidence_ids=frozenset(), playbook_snapshot=snapshot,
    )
    reading = await read_turn(text, text, custom_entries(snapshot))
    kind = reading.get("objection")
    if kind == "none":
        return {"detected": "none", "entry_id": None, "label": None, "card": None, "grounded": False}
    objection_type = kind if kind in turn.OBJECTIONS else None
    entry = _matched_entry(grounding, reading.get("entry_id"))
    result: dict = {}
    async for event in stream_objection_suggestion(
        transcript_window=f"Them: {text}",
        latest_turn=text,
        product_context=product_context or None,
        language="auto",
        call_mode=CALL_MODE,
        speaker_role="prospect",
        grounding=grounding,
        company_knowledge=knowledge,
        contact_history=None,
        objection_type=objection_type,
        entry=entry,
        today=today_line(),
        filler=None,
        previous_answers=[],
    ):
        if event.get("type") == "result":
            result = event
    suggestion = result.get("suggestion") or {}
    say_this = str(suggestion.get("say_this") or "").strip()
    card = (
        {"say_this": say_this, "source_id": suggestion.get("source_id"), "objection_type": suggestion.get("objection_type") or objection_type}
        if say_this else None
    )
    return {
        "detected": kind or "unknown",
        "entry_id": (entry or {}).get("entry_id"),
        "label": (entry or {}).get("label"),
        "card": card,
        "grounded": bool(result.get("grounded")),
    }


# --- part 3: verdicts, result and activation -----------------------------------------------------------------

VERDICTS = frozenset({"approve", "corrected", "unknown", "never_say", "branch", "own"})
ACTIVATE_AT_PERCENT = 80  # a guide, not a lock: below it the Head of Sales is warned and may still activate
MIN_FOR_PERCENT = 3
SIMILAR_PROMPT_VERSION = "playbook_trial_similar_v1"
_SIMILAR_PROMPT = Path(__file__).resolve().parents[2] / "prompts" / f"{SIMILAR_PROMPT_VERSION}.md"
LABEL_WORDS = 6
BRANCH_WHEN_CHARS = 80


def add_branch(guidance: str, when: str, text: str) -> str:
    """`guidance` with "Si {when}: {text}" at its end. ValueError("guidance_too_long") when it no longer fits."""
    merged = f"{(guidance or '').strip()} {branch_text(when, text)}".strip()
    if len(merged) > MAX_GUIDANCE:
        raise ValueError("guidance_too_long")
    return merged


def _find_objection(objections: list[dict], entry_id: str | None) -> dict | None:
    """The editor objection an entry id (`objection:price`, `objection:custom:<slug>`) names."""
    if not entry_id:
        return None
    if entry_id.startswith("objection:custom:"):
        wanted = entry_id.split(":", 2)[2]
        return next(
            (o for o in objections if o.get("category") == CUSTOM_CATEGORY and (o.get("id") == wanted or slug(str(o.get("label") or ""), "custom") == wanted)),
            None,
        )
    category = entry_id.split(":", 1)[1] if entry_id.startswith("objection:") else entry_id
    return next((o for o in objections if o.get("category") == category), None)


def _own_objection(objections: list[dict], case: dict, body: str) -> tuple[dict, str]:
    """A new objection of the team's own for what the customer said: named after the first words, with the phrase as
    the way the prospect says it."""
    customs = [o for o in objections if o.get("category") == CUSTOM_CATEGORY]
    if len(customs) >= MAX_CUSTOM_OBJECTIONS:
        raise ValueError("too_many_custom_objections")
    base = clip_text(" ".join(str(case.get("client_text") or "").split()[:LABEL_WORDS]), MAX_OBJECTION_LABEL) or "Objeción"
    taken = {str(o.get("label") or "").strip().casefold() for o in customs}
    label, n = base, 2
    while label.casefold() in taken:
        label, n = f"{base} {n}", n + 1
    objection = {
        "category": CUSTOM_CATEGORY, "id": slug(label, "custom"), "label": label,
        "trigger": clip_text(" ".join(str(case.get("client_text") or "").split()), MAX_TRIGGER), "guidance": body,
    }
    return objection, f"objection:custom:{objection['id']}"


def apply_verdict(editor: dict, case: dict, entry_id: str | None, verdict: str, text: str | None, *, when: str | None = None) -> dict:
    """The editor content after a verdict -> {steps, objections, qualification, entry_id}; the objections are new
    dicts, nothing passed in is changed. `entry_id` is the answer the card followed (None when it followed none).
      approve / unknown   nothing changes;
      corrected           the answer becomes `text` (an own objection is created when there was none);
      never_say           " No digas: …" is added to the answer;
      branch              "Si {when}: …" is added to the answer;
      own                 `text` is kept as an objection of its own, named after `when` (a branch that did not fit).
    ValueError: text_required, guidance_too_long, no_answer_to_attach, too_many_custom_objections."""
    objections = [dict(o) for o in editor.get("objections") or []]
    result_id = entry_id
    if verdict not in ("approve", "unknown"):
        body = (text or "").strip()
        if not body:
            raise ValueError("text_required")
        target = _find_objection(objections, entry_id)
        if verdict == "never_say":
            if target is None:
                raise ValueError("no_answer_to_attach")
            merged = f"{str(target.get('guidance') or '').strip()} No digas: {body.rstrip('.')}.".strip()
            if len(merged) > MAX_GUIDANCE:
                raise ValueError("guidance_too_long")
            target["guidance"] = merged
        elif verdict == "own":
            if len(body) > MAX_GUIDANCE:
                raise ValueError("guidance_too_long")
            created, result_id = _own_objection(objections, {"client_text": when or case.get("client_text")}, body)
            objections.append(created)
        elif verdict == "branch" and target is not None:
            target["guidance"] = add_branch(str(target.get("guidance") or ""), when or str(case.get("client_text") or "")[:BRANCH_WHEN_CHARS], body)
        else:
            if len(body) > MAX_GUIDANCE:
                raise ValueError("guidance_too_long")
            if target is not None:
                target["guidance"] = body
            elif entry_id and entry_id.startswith("objection:") and entry_id.split(":", 1)[1] in OBJECTION_CATEGORIES:
                objections.append({"category": entry_id.split(":", 1)[1], "guidance": body})
            else:
                created, result_id = _own_objection(objections, case, body)
                objections.append(created)
    return {
        "steps": list(editor.get("steps") or []), "objections": objections,
        "qualification": list(editor.get("qualification") or []), "entry_id": result_id,
    }


def trial_result(decided: list[dict]) -> dict:
    """How the trial went, from [{verdict, topic}] of the cases decided so far -> {approved, total, percent | None,
    weak_topics, warn, can_activate}. A percentage needs MIN_FOR_PERCENT cases; below ACTIVATE_AT_PERCENT the screen
    warns, and activating is allowed anyway (`can_activate` is always true)."""
    total = len(decided)
    approved = sum(1 for item in decided if item.get("verdict") == "approve")
    percent = round(approved / total * 100) if total >= MIN_FOR_PERCENT else None
    weak = Counter(str(item.get("topic") or "") for item in decided if item.get("verdict") != "approve" and item.get("topic"))
    first = {topic: index for index, topic in enumerate(dict.fromkeys(str(i.get("topic") or "") for i in decided))}
    topics = sorted(weak, key=lambda topic: (-weak[topic], first[topic]))
    return {
        "approved": approved, "total": total, "percent": percent, "weak_topics": topics,
        "warn": percent is not None and percent < ACTIVATE_AT_PERCENT, "can_activate": True,
    }


@lru_cache(maxsize=1)
def _similar_prompt() -> str:
    return _SIMILAR_PROMPT.read_text(encoding="utf-8")


async def similar_phrase(case: dict, lang: str, *, llm: Any = None) -> str:
    """One different thing a customer could say that raises the same kind of objection or question, to see whether a
    correction holds. "" when the model fails or only repeats the original: the trial goes on without it."""
    text = str(case.get("client_text") or "")
    user = f"Company language: {'English' if lang == 'en' else 'Spanish'}\n\nOriginal phrase:\n\"\"\"\n{text}\n\"\"\""
    messages = [{"role": "system", "content": _similar_prompt()}, {"role": "user", "content": user}]
    try:
        raw = await asyncio.wait_for(_ask(_client(llm), messages, timeout_for(text)), timeout_for(text) + 5)
    except Exception as exc:
        logger.warning("similar phrase not written: %s", type(exc).__name__)
        return ""
    phrase = clip_text(" ".join(str(raw.get("phrase") or "").split()), MAX_CASE_CHARS) if isinstance(raw, dict) else ""
    return "" if not phrase or _fold(phrase) == _fold(text) else phrase


def activate(repository: Any, membership: Any, motion_keys: list[str]) -> dict:
    """Publishes the drafts of the call types the trial touched -> {published: [keys], failed: [{key, code}]}. A type
    that cannot be published (no pending draft, a contradiction) is reported, and the others are still published."""
    published: list[str] = []
    failed: list[dict] = []
    for key in dict.fromkeys(motion_keys):
        try:
            repository.publish(membership.company_id, key)
            published.append(key)
        except PublishError as exc:
            failed.append({"key": key, "code": exc.code})
    return {"published": published, "failed": failed}
