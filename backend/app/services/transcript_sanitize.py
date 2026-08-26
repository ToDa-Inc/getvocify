"""Post-STT repair: deterministic aliases, then Gemini turn/ASR repair.

The LLM may respell allowed entities and reassign obvious speaker flips.
It must not summarize, invent, or replace a spoken name with the CRM name
(Jean stays Jean even if the contact page is Eneritz).
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import unicodedata
from collections import Counter, defaultdict
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

DISPLAY_TRANSCRIPT_STATUSES = frozenset(
    {"extracting", "pending_review", "pending_transcript"}
)


def should_refresh_display_transcript(status: Optional[str]) -> bool:
    """LLM polish may update the shown transcript only before approve/fail."""
    return (status or "") in DISPLAY_TRANSCRIPT_STATUSES


def extraction_complete_update(extraction: dict[str, Any], processed_at: str) -> dict[str, Any]:
    """Persist fields + note. Do not write transcript — polish may already have."""
    return {
        "status": "pending_review",
        "extraction": extraction,
        "processed_at": processed_at,
        "processing_started_at": None,
    }

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


def collapse_extra_speakers(transcript: str, max_parties: int = 2) -> str:
    """Keep the two longest speakers; fold the rest into the shorter kept side."""
    if max_parties < 2:
        return transcript
    turns = parse_transcript_turns(transcript)
    labeled = [t for t in turns if normalize_speaker(t.get("speaker"))]
    counts: Counter[str] = Counter()
    for turn in labeled:
        speaker = normalize_speaker(turn.get("speaker")) or ""
        counts[speaker] += len(str(turn.get("text") or ""))
    if len(counts) <= max_parties:
        return transcript
    keep = [name for name, _ in counts.most_common(max_parties)]
    prospect = keep[-1]
    remapped: list[dict[str, str]] = []
    for turn in turns:
        speaker = normalize_speaker(turn.get("speaker"))
        text = str(turn.get("text") or "").strip()
        if not text:
            continue
        if speaker and speaker not in keep:
            speaker = prospect
        remapped.append({"speaker": speaker, "text": text})
    return serialize_transcript_turns(merge_consecutive_turns(remapped))


def raw_speaker_count(transcript: str) -> int:
    speakers = {
        normalize_speaker(t.get("speaker"))
        for t in parse_transcript_turns(transcript)
        if normalize_speaker(t.get("speaker"))
    }
    return len(speakers)


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


def _fold_key(value: str) -> str:
    nfd = unicodedata.normalize("NFD", value or "")
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn").lower()


# Spoken letter names by language. V is never B ("be"/"bee"/"bê").
_LETTER_NAMES: dict[str, dict[str, str]] = {
    "es": {
        "a": "a",
        "be": "b",
        "ce": "c",
        "de": "d",
        "e": "e",
        "efe": "f",
        "ge": "g",
        "hache": "h",
        "i": "i",
        "jota": "j",
        "ka": "k",
        "ele": "l",
        "eme": "m",
        "ene": "n",
        "o": "o",
        "pe": "p",
        "cu": "q",
        "erre": "r",
        "ese": "s",
        "te": "t",
        "u": "u",
        "uve": "v",
        "doble uve": "w",
        "uve doble": "w",
        "doble u": "w",
        "equis": "x",
        "i griega": "y",
        "ye": "y",
        "zeta": "z",
        "enie": "ñ",
    },
    "en": {
        "ay": "a",
        "bee": "b",
        "cee": "c",
        "dee": "d",
        "ee": "e",
        "ef": "f",
        "gee": "g",
        "aitch": "h",
        "eye": "i",
        "jay": "j",
        "kay": "k",
        "el": "l",
        "em": "m",
        "en": "n",
        "oh": "o",
        "pee": "p",
        "cue": "q",
        "ar": "r",
        "ess": "s",
        "tee": "t",
        "you": "u",
        "vee": "v",
        "double u": "w",
        "ex": "x",
        "why": "y",
        "zee": "z",
        "zed": "z",
    },
    "pt": {
        "a": "a",
        "be": "b",
        "ce": "c",
        "de": "d",
        "e": "e",
        "efe": "f",
        "ge": "g",
        "aga": "h",
        "i": "i",
        "jota": "j",
        "ka": "k",
        "ele": "l",
        "eme": "m",
        "ene": "n",
        "o": "o",
        "pe": "p",
        "que": "q",
        "erre": "r",
        "esse": "s",
        "te": "t",
        "u": "u",
        "ve": "v",
        "dablio": "w",
        "xis": "x",
        "ipsilon": "y",
        "ze": "z",
    },
    "fr": {
        "a": "a",
        "be": "b",
        "ce": "c",
        "de": "d",
        "e": "e",
        "effe": "f",
        "ge": "g",
        "ache": "h",
        "i": "i",
        "ji": "j",
        "ka": "k",
        "elle": "l",
        "emme": "m",
        "enne": "n",
        "o": "o",
        "pe": "p",
        "ku": "q",
        "erre": "r",
        "esse": "s",
        "te": "t",
        "u": "u",
        "ve": "v",
        "double ve": "w",
        "ixe": "x",
        "i grec": "y",
        "zede": "z",
    },
}
_LETTER_NAMES["ca"] = dict(_LETTER_NAMES["es"])
_AT_WORDS = {
    "es": frozenset({"arroba"}),
    "ca": frozenset({"arroba", "arrova"}),
    "en": frozenset({"at"}),
    "pt": frozenset({"arroba"}),
    "fr": frozenset({"arobase", "arobas"}),
}
_DOT_WORDS = {
    "es": frozenset({"punto"}),
    "ca": frozenset({"punt", "punto"}),
    "en": frozenset({"dot"}),
    "pt": frozenset({"ponto"}),
    "fr": frozenset({"point"}),
}


def _email_lang(spoken_language: Optional[str]) -> str:
    lang = (spoken_language or "es").strip().lower().split("-")[0]
    if lang in _LETTER_NAMES:
        return lang
    return "es"


def spelled_email_guidelines(spoken_language: Optional[str]) -> str:
    """How to reconstruct letter-by-letter emails for the spoken language."""
    lang = _email_lang(spoken_language)
    if lang == "en":
        return """
Spelled emails: write the address (do not leave it as letter names).
English letter names only — V is "vee", never "bee". B is "bee".
"at" = @, "dot" = ".".
"D A N I AT GMAIL DOT COM" → dani@gmail.com
"JAY AY VEE EYE E AR DOT VEE AY EL EL E AT GMAIL DOT COM" → javier.valle@gmail.com
Do not invent an address that was not spelled or spoken.
"""
    if lang == "pt":
        return """
Emails soletrados: escreve o endereço (não deixes as letras faladas).
V é "vê", nunca "bê". B é "bê". "arroba" = @, "ponto" = ".".
"DÊ A ENE I ARROBA GMAIL PONTO COM" → dani@gmail.com
Não inventes um email que não foi soletrado.
"""
    if lang == "fr":
        return """
Emails épétés: écris l'adresse (pas les noms de lettres).
V = "vé", jamais "bé". B = "bé". "arobase" = @, "point" = ".".
"DÉ A ENNE I AROBASE GMAIL POINT COM" → dani@gmail.com
N'invente pas une adresse qui n'a pas été épelée.
"""
    return """
Spelled emails: reconstruct the written address in the turn (do not leave letter names).
Spanish letter names only — never NATO, never English letter names.
V is "uve", NEVER "be". B is "be".
"arroba" = @, "punto" = ".".
"DE, A, ENE, I, ARROBA GMAIL PUNTO COM" → dani@gmail.com
"JOTA, A, UVE, I, E, ERRE, PUNTO, UVE, A, ELE, ELE, E, ARROBA GMAIL PUNTO COM" → javier.valle@gmail.com
"efe Gallardo arroba Ascale punto es" → fgallardo@ascale.es
Do not invent an address that was not spelled or spoken.
"""


def _email_tables(lang: str) -> tuple[dict[str, str], frozenset[str], frozenset[str]]:
    letters = {_fold_key(k): v for k, v in _LETTER_NAMES[lang].items()}
    at_words = _AT_WORDS.get(lang) or _AT_WORDS["es"]
    dot_words = _DOT_WORDS.get(lang) or _DOT_WORDS["es"]
    return letters, at_words, dot_words


_TOKEN_RE = re.compile(r"SPEAKER:|S\d+\b|[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+|@|\.", re.IGNORECASE)


def reconstruct_spelled_emails(
    transcript: str,
    spoken_language: Optional[str] = None,
) -> str:
    """Turn spoken letter-by-letter emails into written addresses. Language-specific."""
    if not transcript or not str(transcript).strip():
        return transcript
    lang = _email_lang(spoken_language)
    letters, at_words, dot_words = _email_tables(lang)
    tokens = list(_TOKEN_RE.finditer(transcript))
    if not tokens:
        return transcript

    def kind_value(raw: str) -> tuple[str, str]:
        folded = _fold_key(raw)
        if raw == "@" or folded in at_words:
            return "at", "@"
        if folded in dot_words:
            return "dot", "."
        if raw == ".":
            return "punct", "."
        if folded in {"speaker"} or folded.startswith("speaker") or re.fullmatch(r"s\d+", folded):
            return "skip", raw
        if folded in letters:
            return "letter", letters[folded]
        if len(folded) == 1 and folded.isalpha():
            return "letter", folded
        return "word", folded

    parsed: list[tuple[int, int, str, str]] = []
    for match in tokens:
        kind, value = kind_value(match.group())
        parsed.append((match.start(), match.end(), kind, value))

    filler = _STOP | {"ok", "okay", "vale", "bueno", "mira", "pues", "yeah", "yes"}
    replacements: list[tuple[int, int, str]] = []
    used: set[int] = set()
    for i, (_, _, kind, _) in enumerate(parsed):
        if kind != "at" or i in used:
            continue
        left: list[str] = []
        start_i = i
        j = i - 1
        while j >= 0 and (i - j) <= 28:
            _s, _e, k, v = parsed[j]
            if k == "skip" or (k == "word" and v in filler) or k == "punct":
                j -= 1
                continue
            if k in {"letter", "dot"}:
                left.append(v)
                start_i = j
                j -= 1
                continue
            if k == "word" and v and v.isalpha() and len(v) >= 3 and not left:
                k2 = j - 1
                while k2 >= 0 and parsed[k2][2] in {"skip", "punct"}:
                    k2 -= 1
                if k2 >= 0 and parsed[k2][2] == "letter" and len(parsed[k2][3]) == 1:
                    left.append(v)
                    start_i = j
                    left.append(parsed[k2][3])
                    start_i = k2
                break
            break
        left.reverse()
        right: list[str] = []
        end_i = i
        j = i + 1
        while j < len(parsed) and (j - i) <= 16:
            _s, _e, k, v = parsed[j]
            if k == "skip" or k == "punct":
                if k == "punct":
                    right.append(".")
                    end_i = j
                j += 1
                continue
            if k in {"letter", "dot", "word"}:
                already = "".join(right).strip(".")
                if already and re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,8}", already) and k == "word" and len(v) > 3:
                    break
                right.append(v)
                end_i = j
                j += 1
                continue
            break
        local = "".join(left).strip(".")
        domain = "".join(right).strip(".")
        if len(local) < 2 or "." not in domain or "@" in local:
            continue
        if not re.fullmatch(r"[a-z0-9._%+-]+", local):
            continue
        if not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,8}", domain):
            continue
        email = f"{local}@{domain}"
        replacements.append((parsed[start_i][0], parsed[end_i][1], email))
        used.update(range(start_i, end_i + 1))

    if not replacements:
        return transcript
    out = transcript
    for start, end, email in reversed(replacements):
        out = out[:start] + email + out[end:]
    return out


def build_sanitize_llm_prompt(
    transcript: str,
    terms: Iterable[EntityTerm],
    roles: Optional[dict[str, str]] = None,
    spoken_language: Optional[str] = None,
) -> str:
    entity_block = format_terms_for_llm(terms) or "(none provided)"
    roles = roles or {}
    rep = roles.get("rep_name") or "the Vocify user / sales rep"
    them = roles.get("contact_name") or "the prospect"
    company = roles.get("company_name") or "the prospect company"
    seller = roles.get("seller_company") or "the seller company"
    lang = (spoken_language or "").strip().lower()
    language_block = ""
    if lang == "ca":
        language_block = """
Spoken language is Catalan (may mix Spanish). Keep Catalan orthography.
Do not translate into Spanish. Fix ASR toward Catalan (trucadas→trucades, tienes→tens, vacaciones→vacances, vosotros→vosaltres).
"""
    elif lang == "es":
        language_block = """
Spoken language is Spanish. Repair toward Spanish; do not rewrite into Catalan.
"""
    email_block = spelled_email_guidelines(spoken_language)
    return f"""You repair a sales-call transcript after automatic speech recognition.
{language_block}
{email_block}
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
4. Reconstruct spelled emails into the written address (see the spelling rules above).

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
    spoken_language: Optional[str] = None,
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
                    "You never summarize, translate, or invent. Return JSON with a turns array."
                ),
            },
            {
                "role": "user",
                "content": build_sanitize_llm_prompt(
                    transcript, term_list, roles, spoken_language=spoken_language
                ),
            },
        ]
        from app.services.pipeline_meta import snapshot_prompts

        _SANITIZE_LLM.set(
            {
                "provider": getattr(settings, "LLM_PROVIDER", None) or "openrouter",
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
        call_meta = getattr(llm, "last_call_meta", None) or {}
        info = dict(_SANITIZE_LLM.get() or {})
        if call_meta.get("model"):
            info["model"] = call_meta["model"]
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            if call_meta.get(key) is not None:
                info[key] = call_meta[key]
        _SANITIZE_LLM.set(info)
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
    spoken_language: Optional[str] = None,
    two_party: bool = False,
) -> tuple[str, str]:
    """Deterministic aliases, casing, S1/S2 remap, spelled emails. No LLM — safe before extract."""
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
    text = cleaned.text
    if two_party:
        text = collapse_extra_speakers(text)
    text = canonicalize_rep_prospect_speakers(text, roles)
    if not spoken_language:
        try:
            from app.services.session_entities import get_batch_stt_language

            spoken_language = get_batch_stt_language()
        except Exception:
            spoken_language = None
    text = reconstruct_spelled_emails(text, spoken_language=spoken_language)
    return text, format_terms_for_llm(terms)


async def prepare_transcript_for_extraction_async(
    transcript: str,
    glossary: Optional[list[dict[str, Any]]] = None,
    existing_values: Optional[dict[str, Any]] = None,
    extra_names: Optional[list[str]] = None,
    spoken_language: Optional[str] = None,
    two_party: bool = False,
) -> tuple[str, str]:
    """Cheap repair, then optional LLM polish for display (do not block extract on this)."""
    from app.services.pipeline_meta import record_stage

    t0 = time.perf_counter()
    token = _SANITIZE_LLM.set(None)
    try:
        if not spoken_language:
            try:
                from app.services.session_entities import get_batch_stt_language

                spoken_language = get_batch_stt_language()
            except Exception:
                spoken_language = None
        text, glossary_text = prepare_transcript_for_extraction(
            transcript,
            glossary,
            existing_values,
            extra_names,
            spoken_language=spoken_language,
            two_party=two_party,
        )
        terms = collect_sanitize_terms(glossary, existing_values, extra_names)
        roles = role_hints_from_context(existing_values, extra_names)
        polished = await llm_sanitize_transcript(
            text, terms, roles, spoken_language=spoken_language
        )
        if two_party:
            polished = collapse_extra_speakers(polished)
        polished = canonicalize_rep_prospect_speakers(polished, roles)
        polished = reconstruct_spelled_emails(polished, spoken_language=spoken_language)
        info = _SANITIZE_LLM.get() or {}
        record_stage("sanitize", t0, **info)
        return polished, glossary_text
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
    """Load glossary + CRM names, then cheap deterministic repair (no LLM)."""
    from app.services.glossary import GlossaryService
    from app.services.session_entities import load_stt_profile

    glossary_svc = GlossaryService(supabase)
    glossary = await glossary_svc.get_user_glossary(user_id)
    profile = load_stt_profile(supabase, user_id)
    extra = [n for n in (profile.get("full_name"), profile.get("company_name")) if n]
    langs = profile.get("stt_languages") or ["es"]
    spoken = langs[0] if langs else "es"
    values = existing_values
    if values is None and memo_data is not None:
        try:
            from app.services.extraction_context import load_existing_crm_values

            values = await load_existing_crm_values(supabase, user_id, memo_data)
        except Exception:
            values = {}
    source = (memo_data or {}).get("source") or (memo_data or {}).get("source_type") or ""
    cleaned, _ = prepare_transcript_for_extraction(
        transcript,
        glossary,
        values,
        extra_names=extra,
        spoken_language=spoken,
        two_party=source == "hubspot_call",
    )
    return cleaned


async def polish_memo_transcript(
    memo_id: str,
    user_id: str,
    transcript: str,
    supabase: Any,
    *,
    memo_data: Optional[dict[str, Any]] = None,
) -> None:
    """Background LLM repair of the stored transcript. Never blocks extract or overwrites CRM fields."""
    if not transcript or not str(transcript).strip():
        return
    try:
        from app.services.glossary import GlossaryService
        from app.services.session_entities import load_stt_profile

        glossary_svc = GlossaryService(supabase)
        glossary = await glossary_svc.get_user_glossary(user_id)
        profile = load_stt_profile(supabase, user_id)
        extra = [n for n in (profile.get("full_name"), profile.get("company_name")) if n]
        if memo_data is None:
            fetched = (
                supabase.table("memos")
                .select(
                    "id,user_id,hubspot_contact_id,hubspot_deal_id,matched_deal_id,status,source,source_type"
                )
                .eq("id", memo_id)
                .limit(1)
                .execute()
            )
            memo_data = (fetched.data or [None])[0]
        values = None
        if memo_data is not None:
            try:
                from app.services.extraction_context import load_existing_crm_values

                values = await load_existing_crm_values(supabase, user_id, memo_data)
            except Exception:
                values = {}
        langs = profile.get("stt_languages") or ["es"]
        spoken = langs[0] if langs else "es"
        from app.services.pipeline_meta import persist_pipeline_meta, pipeline_run

        with pipeline_run() as stages:
            source = (memo_data or {}).get("source") or (memo_data or {}).get("source_type") or ""
            polished, _ = await prepare_transcript_for_extraction_async(
                transcript,
                glossary,
                values,
                extra_names=extra,
                spoken_language=spoken,
                two_party=source == "hubspot_call",
            )
            persist_pipeline_meta(supabase, memo_id, stages)
        if not polished or polished == transcript:
            return
        row = (
            supabase.table("memos")
            .select("status")
            .eq("id", memo_id)
            .limit(1)
            .execute()
        )
        status = ((row.data or [None])[0] or {}).get("status")
        if not should_refresh_display_transcript(status):
            return
        supabase.table("memos").update({"transcript": polished}).eq("id", memo_id).execute()
    except Exception as e:
        logger.warning("Background transcript polish skipped for %s: %s", memo_id, e)


_POLISH_TASKS: set[asyncio.Task] = set()


def schedule_transcript_polish(
    memo_id: str,
    user_id: str,
    transcript: str,
    supabase: Any,
    *,
    memo_data: Optional[dict[str, Any]] = None,
) -> None:
    """Fire LLM transcript polish without waiting. Extract proceeds on cheap text."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(
        polish_memo_transcript(
            memo_id, user_id, transcript, supabase, memo_data=memo_data
        )
    )
    _POLISH_TASKS.add(task)
    task.add_done_callback(_POLISH_TASKS.discard)
