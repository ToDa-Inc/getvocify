"""Post-STT repair: deterministic aliases, then Gemini turn/ASR repair.

The LLM may respell allowed entities and reassign obvious speaker flips.
It must not summarize, invent, or replace a spoken name with the CRM name
(Jean stays Jean even if the contact page is Eneritz).
"""

from __future__ import annotations

import logging
import re
import time
import unicodedata
from collections import defaultdict
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from app.services.session_entities import (
    EntityTerm,
    build_page_terms,
    format_terms_for_llm,
    merge_terms,
    terms_from_existing_values,
    terms_from_glossary,
)
from app.services.transcript_turns import (
    merge_consecutive_turns,
    normalize_diarized_transcript,
    normalize_speaker,
    parse_transcript_turns,
    serialize_transcript_turns,
)

logger = logging.getLogger(__name__)

_SANITIZE_LLM: ContextVar[Optional[dict[str, Any]]] = ContextVar(
    "sanitize_llm_info", default=None
)

_STOP = frozenset(
    {
        "a",
        "an",
        "and",
        "at",
        "con",
        "de",
        "el",
        "en",
        "hey",
        "hola",
        "in",
        "is",
        "la",
        "las",
        "los",
        "no",
        "of",
        "ok",
        "on",
        "or",
        "para",
        "por",
        "si",
        "the",
        "to",
        "un",
        "una",
        "y",
        "yes",
    }
)


@dataclass
class SanitizeResult:
    text: str
    replacements: list[tuple[str, str]] = field(default_factory=list)


def _alias_ok(alias: str, canonical: str) -> bool:
    a = alias.strip()
    if not a or a.lower() == canonical.lower():
        return True
    if a.lower() in _STOP:
        return False
    return len(a) >= 3


def _word_pattern(alias: str) -> re.Pattern[str]:
    escaped = re.escape(alias)
    return re.compile(rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE)


def sanitize_transcript(text: str, terms: Iterable[EntityTerm]) -> SanitizeResult:
    """Replace known mishears and normalize casing. Leave everything else alone."""
    if not text:
        return SanitizeResult(text=text or "")

    replacements: list[tuple[str, str]] = []
    pairs: list[tuple[str, str]] = []
    for term in terms:
        if not term.canonical:
            continue
        for alias in (*term.aliases, term.canonical):
            if not _alias_ok(alias, term.canonical):
                continue
            pairs.append((alias, term.canonical))

    pairs.sort(key=lambda p: len(p[0]), reverse=True)
    seen_alias: set[str] = set()
    out = text
    for alias, canonical in pairs:
        key = alias.lower()
        if key in seen_alias:
            continue
        seen_alias.add(key)
        pattern = _word_pattern(alias)
        next_text, n = pattern.subn(canonical, out)
        if n and next_text != out:
            replacements.append((alias, canonical))
            out = next_text
    return SanitizeResult(text=out, replacements=replacements)


def collect_sanitize_terms(
    glossary: Optional[list[dict[str, Any]]] = None,
    existing_values: Optional[dict[str, Any]] = None,
    extra_names: Optional[list[str]] = None,
) -> list[EntityTerm]:
    """Glossary + CRM/page names (contact, company, deal) + caller."""
    return merge_terms(
        terms_from_glossary(glossary),
        terms_from_existing_values(existing_values),
        build_page_terms(extra_names=extra_names or []),
    )


def role_hints_from_context(
    existing_values: Optional[dict[str, Any]] = None,
    extra_names: Optional[list[str]] = None,
) -> dict[str, str]:
    contacts = (existing_values or {}).get("contacts") or {}
    companies = (existing_values or {}).get("companies") or {}
    deals = (existing_values or {}).get("deals") or {}
    extras = [n for n in (extra_names or []) if n]
    contact = f"{contacts.get('firstname') or ''} {contacts.get('lastname') or ''}".strip()
    return {
        "rep_name": extras[0] if extras else "",
        "seller_company": extras[1] if len(extras) > 1 else "",
        "contact_name": contact,
        "company_name": str(companies.get("name") or ""),
        "deal_name": str(deals.get("dealname") or deals.get("name") or ""),
    }


def _fold_text(value: str) -> str:
    nfkd = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch)).lower()


def _first_token(value: str) -> str:
    parts = (value or "").strip().split()
    return parts[0] if parts else ""


def _has_word(blob: str, word: str) -> bool:
    token = _fold_text(word)
    if not token or len(token) < 3:
        return False
    return bool(re.search(rf"\b{re.escape(token)}\b", blob))


def _names_overlap(a: str, b: str) -> bool:
    """toni↔antoni, dani↔danny. Do not treat Maria as a match for Mariana unless equal."""
    x, y = _fold_text(a), _fold_text(b)
    if not x or not y or min(len(x), len(y)) < 3:
        return False
    if x == y:
        return True
    shorter, longer = (x, y) if len(x) <= len(y) else (y, x)
    if len(shorter) < 4:
        return longer.startswith(shorter) or shorter in longer
    return shorter in longer


_SOY_NAME = re.compile(r"\b(?:soy|me llamo)\s+([a-z]{3,})\b")
_REP_PITCH = (
    r"\bfundador(?:a)?(?:\s+de)?\b",
    r"\bte llamo\b",
    r"\bte estoy llamando\b",
    r"\bpara darte contexto\b",
    r"\babr[ií] el mercado\b",
)
_PROSPECT_REPLY = (
    r"\bqui[eé]n dices que eres",
    r"\bno te estoy escuchando",
    r"\bno s[eé] qui[eé]n",
    r"\bno,? la verdad,? no",
    r"\bno te ubico",
    r"\bd[ií]game qu[eé] necesitas",
    r"\bqu[eé] necesitas\b",
)


def _rep_turn_score(text: str, roles: dict[str, str]) -> int:
    blob = _fold_text(text)
    if not blob:
        return 0
    score = 0
    rep_first = _first_token(roles.get("rep_name") or "")
    contact_first = _first_token(roles.get("contact_name") or "")
    seller = roles.get("seller_company") or ""

    spoken = _SOY_NAME.search(blob)
    if spoken:
        name = spoken.group(1)
        if contact_first and _names_overlap(name, contact_first):
            score -= 2
        elif _names_overlap(name, rep_first) or re.search(r"\bfundador", blob):
            score += 3
        else:
            score += 2

    if contact_first:
        folded_c = _fold_text(contact_first)
        if re.search(rf"^hola,?\s+{re.escape(folded_c)}\b", blob):
            score += 2
        if re.search(rf"\byo,?\s+{re.escape(folded_c)}\b", blob):
            score -= 3

    if seller and _has_word(blob, seller) and re.search(r"\b(?:soy|fundador|fundadora|startup)\b", blob):
        score += 2
    for pat in _REP_PITCH:
        if re.search(pat, blob, re.IGNORECASE):
            score += 2
            break
    for pat in _PROSPECT_REPLY:
        if re.search(pat, blob, re.IGNORECASE):
            score -= 2
            break
    return score


def canonicalize_rep_prospect_speakers(
    transcript: str,
    roles: Optional[dict[str, str]] = None,
) -> str:
    """On 2-party recordings, map the sales-rep voice to S1 and everyone else to S2.

    HubSpot phone audio often inverts Speechmatics IDs, so S2 gets the pitch
    ('soy Danny, fundador… te llamo Íñigo') while the UI still labels S2 as the contact.
    """
    turns = parse_transcript_turns(transcript)
    labeled = [t for t in turns if normalize_speaker(t.get("speaker"))]
    if len(labeled) < 2:
        return transcript

    roles = roles or {}
    scores: dict[str, int] = defaultdict(int)
    for turn in labeled:
        speaker = normalize_speaker(turn.get("speaker")) or "S?"
        scores[speaker] += _rep_turn_score(str(turn.get("text") or ""), roles)

    if not scores:
        return transcript
    rep_id, best = max(scores.items(), key=lambda item: (item[1], item[0] == "S1"))
    if best < 2:
        return transcript

    remapped: list[dict[str, str]] = []
    for turn in turns:
        speaker = normalize_speaker(turn.get("speaker"))
        text = str(turn.get("text") or "").strip()
        if not text:
            continue
        new_speaker = "S1" if speaker == rep_id else ("S2" if speaker else None)
        remapped.append({"speaker": new_speaker, "text": text})
    return serialize_transcript_turns(merge_consecutive_turns(remapped))


def build_sanitize_llm_prompt(
    transcript: str,
    terms: Iterable[EntityTerm],
    roles: Optional[dict[str, str]] = None,
) -> str:
    entity_block = format_terms_for_llm(terms) or "(none provided)"
    roles = roles or {}
    rep = roles.get("rep_name") or "the Vocify user / sales rep"
    them = roles.get("contact_name") or "the prospect"
    company = roles.get("company_name") or "the prospect company"
    seller = roles.get("seller_company") or "the seller company"
    return f"""You repair a sales-call transcript after automatic speech recognition.

Roles (use these to fix speaker labels, not to invent names):
- S1 = {rep} (the caller / sales rep from {seller})
- S2 = {them} at {company} (the prospect)
- Two-person phone call: do not keep S3/S4. Merge extras into S1 or S2.

ASR speaker IDs on HubSpot/phone recordings are often inverted or split.
If S2 says "soy {rep}" / "fundador" / "te llamo {them}", that pitch is S1 — not {them}.
Never label the pitch as {them} just because the rep said their name.

Allowed entities — spell these exactly ONLY if they were actually spoken:
{entity_block}

Repair:
1. Obvious ASR / phonetic errors on phone audio (SyFy → Vocify if allowed; tocadas → llamadas; cikautcho → Cikautxo).
   Keep messy overlap. Do not rewrite the call into clean prose.
2. Speaker assignment: move or split a turn when the WORDS clearly belong to the other person
   (self-intro as founder = S1; answering discovery / vacation / their stack = S2).
3. Merge consecutive turns from the same speaker. Split a turn that contains both voices.

Do not:
- Summarize, translate, or clean filler/grammar for style.
- Add facts, companies, or people that were not spoken.
- Replace a clearly different spoken name with the CRM name
  (transcript says Jean, contact is Eneritz → leave Jean).
- Invent clean sentences over unintelligible overlap — leave the messy words.

Return JSON only:
{{"turns": [{{"speaker": "S1", "text": "..."}}, {{"speaker": "S2", "text": "..."}}]}}

TRANSCRIPT:
\"\"\"
{transcript}
\"\"\"
"""


def accept_llm_sanitize(original: str, candidate: str) -> bool:
    """Drop LLM output that rewrote or emptied the transcript."""
    src = (original or "").strip()
    out = (candidate or "").strip()
    if not src or not out:
        return False
    if out.startswith("```"):
        out = out.strip("`").strip()
        if out.lower().startswith("text"):
            out = out[4:].lstrip()
    if len(out) < max(20, int(len(src) * 0.55)):
        return False
    if len(out) > int(len(src) * 1.45) + 80:
        return False
    return True


def _strip_llm_transcript(candidate: str) -> str:
    out = (candidate or "").strip()
    if out.startswith("```"):
        lines = out.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        out = "\n".join(lines).strip()
    return out


def turns_from_llm_payload(payload: Any) -> list[dict[str, str]]:
    if isinstance(payload, dict):
        raw_turns = payload.get("turns")
    elif isinstance(payload, list):
        raw_turns = payload
    else:
        raw_turns = None
    if not isinstance(raw_turns, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw_turns:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        speaker = normalize_speaker(item.get("speaker")) or "S1"
        out.append({"speaker": speaker, "text": text})
    return out


async def llm_sanitize_transcript(
    transcript: str,
    terms: Iterable[EntityTerm],
    roles: Optional[dict[str, str]] = None,
) -> str:
    """Gemini repair: names, obvious ASR, and speaker turns. Falls back to input."""
    if not transcript or not transcript.strip():
        return transcript
    term_list = [t for t in terms if t.canonical]
    try:
        from app.config import settings
        from app.services.llm import LLMClient

        if not getattr(settings, "TRANSCRIPT_SANITIZE_LLM", True):
            return transcript
        model = (
            (getattr(settings, "TRANSCRIPT_SANITIZE_MODEL", None) or "").strip()
            or (getattr(settings, "EXTRACTION_MODEL", None) or "").strip()
            or "google/gemini-3.5-flash-lite"
        )
        llm = LLMClient(model=model)
        messages = [
            {
                "role": "system",
                "content": (
                    "You repair ASR transcripts and speaker labels. "
                    "You never summarize or invent. Return JSON with a turns array."
                ),
            },
            {
                "role": "user",
                "content": build_sanitize_llm_prompt(transcript, term_list, roles),
            },
        ]
        from app.services.pipeline_meta import snapshot_prompts

        _SANITIZE_LLM.set(
            {
                "provider": "openrouter",
                "model": model,
                "prompts": snapshot_prompts(messages),
            }
        )
        payload = await llm.chat_json(
            messages,
            model=model,
            temperature=0.0,
            timeout=45.0,
            max_retries=1,
        )
        turns = turns_from_llm_payload(payload)
        cleaned = serialize_transcript_turns(turns) if turns else ""
        if accept_llm_sanitize(transcript, cleaned):
            if cleaned != transcript:
                logger.info(
                    "LLM transcript repair applied (%d → %d chars, %d turns)",
                    len(transcript),
                    len(cleaned),
                    len(turns),
                )
            return cleaned
        logger.warning("LLM transcript repair output rejected (length/shape guard)")
    except Exception as e:
        logger.warning("LLM transcript sanitizer skipped: %s", e)
    return transcript


def prepare_transcript_for_extraction(
    transcript: str,
    glossary: Optional[list[dict[str, Any]]] = None,
    existing_values: Optional[dict[str, Any]] = None,
    extra_names: Optional[list[str]] = None,
) -> tuple[str, str]:
    """Deterministic repair only. Use prepare_transcript_for_extraction_async for the LLM pass."""
    transcript = normalize_diarized_transcript(transcript)
    terms = collect_sanitize_terms(glossary, existing_values, extra_names)
    cleaned = sanitize_transcript(transcript, terms)
    if cleaned.replacements:
        logger.info(
            "Transcript sanitizer applied %d replacement(s): %s",
            len(cleaned.replacements),
            cleaned.replacements[:8],
        )
    roles = role_hints_from_context(existing_values, extra_names)
    text = canonicalize_rep_prospect_speakers(cleaned.text, roles)
    return text, format_terms_for_llm(terms)


async def prepare_transcript_for_extraction_async(
    transcript: str,
    glossary: Optional[list[dict[str, Any]]] = None,
    existing_values: Optional[dict[str, Any]] = None,
    extra_names: Optional[list[str]] = None,
) -> tuple[str, str]:
    """Deterministic aliases/casing, then a cheap LLM pass over page + glossary entities."""
    from app.services.pipeline_meta import record_stage

    t0 = time.perf_counter()
    token = _SANITIZE_LLM.set(None)
    try:
        transcript = normalize_diarized_transcript(transcript)
        terms = collect_sanitize_terms(glossary, existing_values, extra_names)
        cleaned = sanitize_transcript(transcript, terms)
        roles = role_hints_from_context(existing_values, extra_names)
        text = canonicalize_rep_prospect_speakers(cleaned.text, roles)
        text = await llm_sanitize_transcript(text, terms, roles)
        text = canonicalize_rep_prospect_speakers(text, roles)
        info = _SANITIZE_LLM.get() or {}
        record_stage(
            "sanitize",
            t0,
            replacements=len(cleaned.replacements),
            **info,
        )
        return text, format_terms_for_llm(terms)
    finally:
        _SANITIZE_LLM.reset(token)


async def sanitize_user_transcript(
    transcript: str,
    user_id: str,
    supabase: Any,
    *,
    memo_data: Optional[dict[str, Any]] = None,
    existing_values: Optional[dict[str, Any]] = None,
) -> str:
    """Load glossary + CRM names, then apply deterministic repair."""
    from app.services.glossary import GlossaryService
    from app.services.session_entities import load_stt_profile

    glossary_svc = GlossaryService(supabase)
    glossary = await glossary_svc.get_user_glossary(user_id)
    profile = load_stt_profile(supabase, user_id)
    extra = [n for n in (profile.get("full_name"), profile.get("company_name")) if n]
    values = existing_values
    if values is None and memo_data is not None:
        try:
            from app.services.extraction_context import load_existing_crm_values

            values = await load_existing_crm_values(supabase, user_id, memo_data)
        except Exception:
            values = {}
    cleaned, _ = await prepare_transcript_for_extraction_async(
        transcript, glossary, values, extra_names=extra
    )
    return cleaned
