"""Lista 4 T3 (E9): the brief's «gancho de empresa» line. Pure, no I/O, no model call.

Calling Juan at Factorial when someone already talked with Manuel at Factorial: one line
with who, when and one short sentence of that conversation, to open with. The caller
passes only memos the viewer may read; the match is on the company name (memos carry no
CRM company id), normalized so «Factorial HR, S.L.» and «factorial hr» are one company.
"""

from __future__ import annotations

import re
import unicodedata

from app.services.briefs.preparation import plain_sentence
from app.services.briefs.v2 import _as_dt, _day_label, _line
from app.services.followup_logic import pain_quote

MAX_SENTENCE = 140
# Trailing legal forms, after dots are dropped («S.L.U.» -> «slu»).
LEGAL_SUFFIXES = frozenset({
    "sl", "slu", "sll", "sa", "sau", "scp", "sc", "srl", "sas", "sarl", "spa",
    "inc", "incorporated", "corp", "corporation", "co", "company", "llc", "llp", "lp",
    "ltd", "limited", "plc", "gmbh", "ag", "kg", "bv", "nv", "ab", "oy", "as",
})


def normalize_company_name(name) -> str:
    """casefold, no accents, no punctuation, no trailing legal form. Never empties a name
    that is only a legal form."""
    text = unicodedata.normalize("NFKD", str(name or ""))
    text = "".join(char for char in text if not unicodedata.combining(char)).casefold()
    text = text.replace(".", "")
    tokens = re.sub(r"[^\w]+", " ", text).split()
    while len(tokens) > 1 and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def _short(text: str) -> str:
    text = " ".join(text.split())
    if len(text) <= MAX_SENTENCE:
        return text
    cut = text[:MAX_SENTENCE].rsplit(" ", 1)[0].rstrip(" ,;:")
    return f"{cut}…"


def _sentence(memo: dict) -> str | None:
    extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
    summary = plain_sentence(extraction.get("summary"))
    if summary:
        return _short(summary)
    intelligence = extraction.get("intelligence") if isinstance(extraction.get("intelligence"), dict) else {}
    quote = " ".join(str(pain_quote(intelligence) or "").split())
    return f"«{_short(quote)}»" if quote else None


def company_hook_line(
    *,
    company_name,
    colleague_memos: list[dict],
    current_contact_id: str,
    tz_name: str,
    viewer_id: str | None = None,
) -> dict | None:
    """The newest usable memo of ANOTHER CRM contact of the same company, as one line.
    «ya hablaste» when the viewer wrote it, «ya se habló» otherwise."""
    display = " ".join(str(company_name or "").split())
    key = normalize_company_name(display)
    if not key:
        return None
    current = str(current_contact_id or "")

    def when(memo: dict):
        return next(
            (value for value in (memo.get("capture_started_at"), memo.get("created_at")) if _as_dt(value)),
            None,
        )

    candidates = []
    for memo in colleague_memos or []:
        if not isinstance(memo, dict):
            continue
        contact = str(memo.get("hubspot_contact_id") or "")
        if not contact or contact == current:
            continue
        extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
        if normalize_company_name(extraction.get("companyName") or extraction.get("company_name")) != key:
            continue
        at = when(memo)
        if at is None:
            continue
        candidates.append((_as_dt(at), at, memo))
    candidates.sort(key=lambda item: item[0], reverse=True)

    for _parsed, at, memo in candidates:
        sentence = _sentence(memo)
        day = _day_label(at, tz_name)
        if not sentence or not day:
            continue
        extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
        name = " ".join(str(extraction.get("contactName") or extraction.get("contact_name") or "").split())
        who = name or "otra persona"
        verb = "ya hablaste" if viewer_id and str(memo.get("user_id") or "") == str(viewer_id) else "ya se habló"
        text = f"En {display} {verb} con {who} el {day}: {sentence}"
        return _line("company", text, source_ref=memo.get("id"), observed_at=at)
    return None
