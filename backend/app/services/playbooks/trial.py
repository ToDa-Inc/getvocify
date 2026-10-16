"""The trial ("La prueba"): the Head of Sales sees how Vocify would answer what customers say, and corrects it.

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

from app.services.playbooks.structure import _ask, _client, _fold, timeout_for
from app.services.playbooks.structured import clip_text

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
