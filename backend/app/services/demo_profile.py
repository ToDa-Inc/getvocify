"""The company a sales demo plays for.

In a demo the rep sells the product of the company being demoed, to a buyer from its typical customers. While a
profile is live for a user, live help answers as that company: its offer, what it knows (from its website) and one
approved answer per objection the demo buyer raises, in place of the user's own playbook. It expires by itself.
Only companies with DEMO_BUYER_ENABLED ever read it; everyone else's live help is untouched.
"""

from __future__ import annotations

import logging
import re
import threading
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.services.feature_flags import is_enabled

logger = logging.getLogger(__name__)

FLAG = "DEMO_BUYER_ENABLED"
TABLE = "demo_profiles"
TTL = timedelta(hours=6)
CACHE_SECONDS = 20.0
# The objection kinds live help has one approved answer for each: `objection:<kind>`.
FIXED_KINDS = ("price", "timing", "authority", "competitor", "status_quo", "trust")

_cache: dict[str, tuple[float, Optional["DemoOverrides"]]] = {}
_lock = threading.Lock()


class DemoProfileError(Exception):
    """The profile could not be stored (typically the migration is not applied yet)."""


@dataclass(frozen=True)
class DemoOverrides:
    product_context: str
    knowledge: dict
    snapshot: dict
    custom: dict[str, dict[str, str]]


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _slug(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", plain.lower()).strip("_")[:48] or "objecion"


def entries_from_objections(objections: list[dict]) -> list[dict]:
    """Playbook entries for the demo's objections. The first of each fixed kind takes that kind's own id (the
    objection check files it there); every other one is the team's own, matched by what the buyer says."""
    used: set[str] = set()
    taken: set[str] = set()
    entries: list[dict] = []
    for item in objections:
        label, trigger, guidance = _clean(item.get("label")), _clean(item.get("line")), _clean(item.get("guidance"))
        if not (label and guidance):
            continue
        kind = _clean(item.get("category"))
        if kind in FIXED_KINDS and kind not in used:
            used.add(kind)
            entry_id, category = f"objection:{kind}", kind
        else:
            base = f"objection:custom:{_slug(label)}"
            entry_id, n = base, 2
            while entry_id in taken:
                entry_id, n = f"{base}_{n}", n + 1
            category = "custom"
        taken.add(entry_id)
        entries.append(
            {"entry_id": entry_id, "category": category, "label": label, "trigger": trigger, "guidance": guidance, "source_ref": "demo"}
        )
    return entries


def profile_from(*, company: str, offer: str, knowledge: dict, objections: list[dict]) -> dict:
    return {"company": _clean(company), "offer": _clean(offer), "knowledge": knowledge or {}, "entries": entries_from_objections(objections)}


def overrides_for(profile: dict) -> DemoOverrides:
    entries = [e for e in profile.get("entries") or [] if isinstance(e, dict)]
    company, offer = _clean(profile.get("company")), _clean(profile.get("offer"))
    context = f"{company}: {offer}" if company and offer else (offer or company)
    return DemoOverrides(
        product_context=context,
        knowledge=profile.get("knowledge") if isinstance(profile.get("knowledge"), dict) else {},
        snapshot={"sales_motion_key": "demo", "playbook_id": None, "version_id": None, "steps": [], "entries": entries},
        custom={e["entry_id"]: {"label": e["label"], "trigger": e["trigger"]} for e in entries if e.get("category") == "custom"},
    )


def _forget(user_id: str) -> None:
    with _lock:
        _cache.pop(user_id, None)


def save(supabase: Any, *, user_id: str, company_id: str, profile: dict) -> None:
    row = {
        "user_id": user_id,
        "company_id": company_id,
        "profile": profile,
        "expires_at": (datetime.now(timezone.utc) + TTL).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        supabase.table(TABLE).upsert(row, on_conflict="user_id").execute()
    except Exception as exc:
        logger.warning("demo profile: save failed", exc_info=True)
        raise DemoProfileError("No se pudo guardar el perfil de la demo: ¿está aplicada la migración 081?") from exc
    _forget(user_id)


def clear(supabase: Any, user_id: str) -> None:
    try:
        supabase.table(TABLE).delete().eq("user_id", user_id).execute()
    except Exception:
        logger.warning("demo profile: clear failed", exc_info=True)
    _forget(user_id)


def active(supabase: Any, user_id: str) -> Optional[DemoOverrides]:
    """The live profile of this user, or None. Blocking: run it in a thread. Kept for a few seconds, a missing one
    too: live help asks on every pause. A failed read is no profile, never an error in the middle of a call."""
    now = time.monotonic()
    with _lock:
        hit = _cache.get(user_id)
    if hit and now - hit[0] < CACHE_SECONDS:
        return hit[1]
    found: Optional[DemoOverrides] = None
    try:
        rows = supabase.table(TABLE).select("company_id,profile,expires_at").eq("user_id", user_id).limit(1).execute().data or []
        if rows:
            row = rows[0]
            expires = datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00"))
            if expires > datetime.now(timezone.utc) and is_enabled(supabase, str(row["company_id"]), FLAG):
                found = overrides_for(row["profile"])
    except Exception:
        logger.warning("demo profile: read failed", exc_info=True)
        return None
    with _lock:
        _cache[user_id] = (now, found)
    return found
