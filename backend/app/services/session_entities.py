"""Session entities for STT biasing and conservative transcript repair.

Page/CRM names go into Speechmatics additional_vocab (and Deepgram keyterms).
The same list is reused after STT to fix known phonetic collisions only —
never to invent or swap identities (Jean must not become Eneritz).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^[\d\s+\-().]{6,}$")
_SPLIT_NAME = re.compile(r"\s+")


@dataclass(frozen=True)
class EntityTerm:
    canonical: str
    aliases: tuple[str, ...]
    kind: str  # person | company | deal | product | glossary | caller


def is_spoken_term(value: Optional[str]) -> bool:
    text = (value or "").strip()
    if not text or len(text) < 2:
        return False
    if _EMAIL_RE.match(text) or _PHONE_RE.match(text):
        return False
    return True


def _norm(value: str) -> str:
    return " ".join(value.split()).strip()


def parse_session_vocab_part(part: str) -> Optional[EntityTerm]:
    """Parse `Vocify:SyFy,sci-fi` or `Eneritz` from the live WS query string."""
    raw = (part or "").strip()
    if not raw:
        return None
    if ":" in raw:
        canonical, hint_blob = raw.split(":", 1)
        aliases = tuple(
            h.strip()
            for h in hint_blob.split(",")
            if h.strip() and h.strip().lower() != canonical.strip().lower()
        )
    else:
        canonical, aliases = raw, ()
    canonical = _norm(canonical)
    if not is_spoken_term(canonical):
        return None
    return EntityTerm(canonical=canonical, aliases=aliases, kind="glossary")


def parse_session_vocab(raw: str) -> list[EntityTerm]:
    if not raw:
        return []
    out: list[EntityTerm] = []
    seen: set[str] = set()
    for part in raw.split("|"):
        term = parse_session_vocab_part(part)
        if not term:
            continue
        key = term.canonical.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(term)
    return out


def encode_session_vocab(terms: Iterable[EntityTerm]) -> list[str]:
    encoded: list[str] = []
    seen: set[str] = set()
    for term in terms:
        if not is_spoken_term(term.canonical):
            continue
        key = term.canonical.lower()
        if key in seen:
            continue
        seen.add(key)
        aliases = [a for a in term.aliases if a and a.lower() != key]
        if aliases:
            encoded.append(f"{term.canonical}:{','.join(aliases)}")
        else:
            encoded.append(term.canonical)
    return encoded


def _add_term(
    bucket: dict[str, EntityTerm],
    canonical: Optional[str],
    *,
    kind: str,
    aliases: Iterable[str] = (),
) -> None:
    if not is_spoken_term(canonical):
        return
    name = _norm(canonical or "")
    key = name.lower()
    extra = tuple(
        _norm(a)
        for a in aliases
        if is_spoken_term(a) and _norm(a).lower() != key
    )
    existing = bucket.get(key)
    if existing:
        merged = tuple(dict.fromkeys([*existing.aliases, *extra]))
        bucket[key] = EntityTerm(canonical=existing.canonical, aliases=merged, kind=existing.kind)
        return
    bucket[key] = EntityTerm(canonical=name, aliases=extra, kind=kind)


def _add_person(bucket: dict[str, EntityTerm], full_or_first: Optional[str], last: Optional[str] = None, *, kind: str) -> None:
    first = (full_or_first or "").strip()
    last_n = (last or "").strip()
    if last_n:
        _add_term(bucket, first, kind=kind)
        _add_term(bucket, last_n, kind=kind)
        _add_term(bucket, f"{first} {last_n}".strip(), kind=kind)
        return
    if not first:
        return
    parts = _SPLIT_NAME.split(first)
    if len(parts) >= 2:
        _add_term(bucket, parts[0], kind=kind)
        _add_term(bucket, parts[-1], kind=kind)
        _add_term(bucket, first, kind=kind)
    else:
        _add_term(bucket, first, kind=kind)


def terms_from_glossary(glossary: Optional[list[dict[str, Any]]]) -> list[EntityTerm]:
    bucket: dict[str, EntityTerm] = {}
    for item in glossary or []:
        if not isinstance(item, dict):
            continue
        word = item.get("target_word") or item.get("term") or item.get("content")
        hints = item.get("phonetic_hints") or item.get("sounds_like") or []
        if isinstance(hints, str):
            hints = [hints]
        _add_term(bucket, word, kind="glossary", aliases=hints)
    return list(bucket.values())


def build_page_terms(
    *,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    contact_name: Optional[str] = None,
    company_name: Optional[str] = None,
    deal_name: Optional[str] = None,
    extra_names: Optional[Iterable[str]] = None,
    caller_name: Optional[str] = None,
    seller_company: Optional[str] = None,
    glossary: Optional[list[dict[str, Any]]] = None,
) -> list[EntityTerm]:
    bucket: dict[str, EntityTerm] = {}
    if first_name or last_name:
        _add_person(bucket, first_name, last_name, kind="person")
    elif contact_name:
        _add_person(bucket, contact_name, kind="person")
    _add_term(bucket, company_name, kind="company")
    _add_term(bucket, deal_name, kind="deal")
    _add_person(bucket, caller_name, kind="caller")
    _add_term(bucket, seller_company, kind="company")
    for name in extra_names or []:
        _add_person(bucket, name, kind="person")
    for term in terms_from_glossary(glossary):
        _add_term(bucket, term.canonical, kind=term.kind, aliases=term.aliases)
    return list(bucket.values())


def terms_from_existing_values(existing_values: Optional[dict[str, Any]]) -> list[EntityTerm]:
    if not existing_values:
        return []
    contacts = existing_values.get("contacts") or {}
    deals = existing_values.get("deals") or {}
    companies = existing_values.get("companies") or {}
    return build_page_terms(
        first_name=contacts.get("firstname"),
        last_name=contacts.get("lastname"),
        company_name=companies.get("name"),
        deal_name=deals.get("dealname") or deals.get("name"),
    )


def merge_terms(*groups: Iterable[EntityTerm]) -> list[EntityTerm]:
    bucket: dict[str, EntityTerm] = {}
    for group in groups:
        for term in group:
            _add_term(bucket, term.canonical, kind=term.kind, aliases=term.aliases)
    return list(bucket.values())


def format_terms_for_llm(terms: Iterable[EntityTerm]) -> str:
    items = [t for t in terms if t.canonical]
    if not items:
        return ""
    lines = ["Ground Truth entities (spell these exactly if they appear):"]
    for term in items:
        hint = f" (often misheard as: {', '.join(term.aliases)})" if term.aliases else ""
        lines.append(f"- {term.canonical} [{term.kind}]{hint}")
    return "\n".join(lines)


def format_terms_for_speechmatics(terms: Iterable[EntityTerm]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for term in terms:
        key = term.canonical.lower()
        if key in seen:
            continue
        seen.add(key)
        entry: dict[str, Any] = {"content": term.canonical}
        if term.aliases:
            entry["sounds_like"] = list(term.aliases)
        out.append(entry)
    return out


def format_terms_for_deepgram(terms: Iterable[EntityTerm]) -> list[str]:
    """Nova-3 keyterms: correct spellings only (not the mishears)."""
    out: list[str] = []
    seen: set[str] = set()
    for term in terms:
        key = term.canonical.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(term.canonical)
    return out


def vocab_for_hubspot_context(
    *,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    contact_name: Optional[str] = None,
    company_name: Optional[str] = None,
    deal_name: Optional[str] = None,
    extra_names: Optional[Iterable[str]] = None,
    caller_name: Optional[str] = None,
    seller_company: Optional[str] = None,
) -> list[str]:
    """Spoken names only — no email/phone, first+last split, optional caller."""
    return encode_session_vocab(
        build_page_terms(
            first_name=first_name,
            last_name=last_name,
            contact_name=contact_name,
            company_name=company_name,
            deal_name=deal_name,
            extra_names=extra_names,
            caller_name=caller_name,
            seller_company=seller_company,
        )
    )


def resolve_speechmatics_rt_language(requested: str, override: Optional[str] = None) -> str:
    """Map client `multi` to Speechmatics `auto` (same as batch). Override via env."""
    if override is None:
        try:
            from app.config import settings

            override = (getattr(settings, "SPEECHMATICS_RT_LANGUAGE", None) or "").strip()
        except Exception:
            override = ""
    raw = (requested or "multi").strip().lower()
    if override:
        return override.strip()
    if raw in ("multi", "auto", ""):
        return "auto"
    return raw


STT_LANGUAGE_CODES = ("es", "en", "fr", "de", "it", "pt", "ca")
DEFAULT_STT_LANGUAGES = ["es"]


def normalize_stt_languages(raw: Any) -> list[str]:
    """Keep known ISO 639-1 codes, first unique as primary. Default Spanish."""
    allowed = set(STT_LANGUAGE_CODES)
    out: list[str] = []
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, (list, tuple)):
        values = list(raw)
    else:
        values = []
    for item in values:
        code = str(item or "").strip().lower()
        if code not in allowed or code in out:
            continue
        out.append(code)
    return out or list(DEFAULT_STT_LANGUAGES)


def deepgram_language_code(langs: list[str]) -> str:
    """One language → pin it. Two or more → Nova-3 multilingual `multi`."""
    cleaned = normalize_stt_languages(langs)
    if len(cleaned) == 1:
        return cleaned[0]
    return "multi"


def resolve_batch_language(
    requested: Optional[str] = None,
    user_id: Optional[str] = None,
) -> str:
    """File STT language from an explicit code, else the user's profile languages."""
    raw = (requested or "").strip().lower()
    if raw and raw not in ("", "auto", "multi"):
        return raw if raw in STT_LANGUAGE_CODES else "es"
    langs = list(DEFAULT_STT_LANGUAGES)
    if user_id and user_id != "anonymous":
        try:
            from app.services.glossary import GlossaryService

            profile = load_stt_profile(GlossaryService().supabase, user_id)
            langs = profile.get("stt_languages") or langs
        except Exception as e:
            logger.warning("Could not resolve STT languages for %s: %s", user_id, e)
    if raw == "multi":
        return "multi"
    return deepgram_language_code(langs)


def load_stt_profile(supabase: Any, user_id: Optional[str]) -> dict[str, Any]:
    empty: dict[str, Any] = {
        "full_name": None,
        "company_name": None,
        "glossary": [],
        "stt_languages": list(DEFAULT_STT_LANGUAGES),
    }
    if not user_id or user_id == "anonymous":
        return empty
    try:
        result = (
            supabase.table("user_profiles")
            .select("full_name,company_name,glossary,stt_languages")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return empty
        row = rows[0]
        return {
            "full_name": (row.get("full_name") or None),
            "company_name": (row.get("company_name") or None),
            "glossary": row.get("glossary") or [],
            "stt_languages": normalize_stt_languages(row.get("stt_languages")),
        }
    except Exception as e:
        logger.warning("Could not load STT profile for %s: %s", user_id, e)
        return empty


async def speechmatics_vocab_for_job(
    user_id: Optional[str],
    extra_terms: Optional[Iterable[EntityTerm]] = None,
) -> list[dict[str, Any]]:
    """Glossary + seller name/company + page/contact terms for batch additional_vocab."""
    if not user_id or user_id == "anonymous":
        return format_terms_for_speechmatics(extra_terms or [])
    from app.services.glossary import GlossaryService

    glossary_svc = GlossaryService()
    glossary = await glossary_svc.get_user_glossary(user_id)
    profile = load_stt_profile(glossary_svc.supabase, user_id)
    terms = merge_terms(
        build_page_terms(
            caller_name=profile.get("full_name"),
            seller_company=profile.get("company_name"),
            glossary=glossary,
        ),
        extra_terms or [],
    )
    return format_terms_for_speechmatics(terms)


async def deepgram_keyterms_for_job(
    user_id: Optional[str],
    extra_terms: Optional[Iterable[EntityTerm]] = None,
) -> list[str]:
    """Glossary + seller/page names as Nova-3 keyterms (canonical spellings)."""
    if not user_id or user_id == "anonymous":
        return format_terms_for_deepgram(extra_terms or [])
    from app.services.glossary import GlossaryService

    glossary_svc = GlossaryService()
    glossary = await glossary_svc.get_user_glossary(user_id)
    profile = load_stt_profile(glossary_svc.supabase, user_id)
    terms = merge_terms(
        build_page_terms(
            caller_name=profile.get("full_name"),
            seller_company=profile.get("company_name"),
            glossary=glossary,
        ),
        extra_terms or [],
    )
    return format_terms_for_deepgram(terms)
