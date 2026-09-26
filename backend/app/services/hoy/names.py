"""Contact and company names already extracted on the memo. No I/O."""

from __future__ import annotations

NamePair = tuple[str | None, str | None]


def clean_name(value) -> str | None:
    text = " ".join(str(value or "").split())
    return text or None


def memo_directory(memos: list[dict]) -> tuple[dict[str, NamePair], dict[str, NamePair]]:
    """(by memo id, by contact id). A contact only gets a pair that carries a name."""
    by_memo: dict[str, NamePair] = {}
    by_contact: dict[str, NamePair] = {}
    for memo in memos:
        extraction = memo.get("extraction") if isinstance(memo.get("extraction"), dict) else {}
        pair = (clean_name(extraction.get("contactName")), clean_name(extraction.get("companyName")))
        if memo.get("id"):
            by_memo[str(memo["id"])] = pair
        contact_id = memo.get("hubspot_contact_id")
        if contact_id and pair[0]:
            by_contact[str(contact_id)] = pair
    return by_memo, by_contact


def lookup(directory: tuple[dict[str, NamePair], dict[str, NamePair]], memo_id, contact_id) -> NamePair:
    by_memo, by_contact = directory
    name, company = by_memo.get(str(memo_id), (None, None)) if memo_id else (None, None)
    if not name and contact_id:
        name, company = by_contact.get(str(contact_id), (None, company))
    return name, company
