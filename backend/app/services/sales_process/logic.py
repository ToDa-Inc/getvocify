"""Pure rules of the editable sales process: what a type is for, what role a person's types imply, and keys for new types.

A company's own types carry a `stage`: `first_contact` (it aims at getting a meeting: what a SDR does), `deal` (it moves a
sale forward or closes it: what an AE does) or `other` (a call outside the sales funnel, such as customer service: it is
never scored in coaching and says nothing about a person's role). The rest of the product still talks in `sales_role`, so a person's role is derived
from the stages of the types they run, and every reader keeps working unchanged.
"""

from __future__ import annotations

from typing import Callable, Iterable, Optional

from app.services.playbooks.catalog import catalog_role
from app.services.playbooks.structured import slug

STAGES = ("first_contact", "deal", "other")


def stage_for(key: str, rows: Iterable[dict]) -> str:
    """The stage of a type: the one its company gave it, else what the catalog's role says, else first contact."""
    for row in rows:
        if row.get("key") == key and row.get("stage") in STAGES:
            return row["stage"]
    return "deal" if catalog_role(key) == "ae" else "first_contact"


def role_from_types(types: Optional[list[str]], stage_of: Callable[[str], str]) -> str:
    """sdr when the person only runs first-contact types, ae when only deal types, general otherwise (or when they run all)."""
    stages = {stage_of(key) for key in types or []} - {"other"}
    if stages == {"first_contact"}:
        return "sdr"
    if stages == {"deal"}:
        return "ae"
    return "general"


def assigned_types(raw: Optional[list[str]], existing: Iterable[str]) -> Optional[list[str]]:
    """The types a person runs, without the ones that no longer exist and without repeats. None means every type: nothing
    assigned, or nothing left of what was."""
    keep = set(existing)
    left = [key for key in dict.fromkeys(raw or []) if key in keep]
    return left or None


def slug_key(label: str, taken: Iterable[str]) -> str:
    """"Llamada en frío" -> "llamada_en_frio", or "llamada_en_frio_2" when that key is taken."""
    base, seen, n, candidate = slug(label, "tipo"), set(taken), 2, None
    candidate = base
    while candidate in seen:
        candidate, n = f"{base}_{n}", n + 1
    return candidate
