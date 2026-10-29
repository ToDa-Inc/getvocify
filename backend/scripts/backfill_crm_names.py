"""Name a user's saved calls after their CRM contact and company, as new calls are named.

Usage (from backend/): .venv/bin/python scripts/backfill_crm_names.py <user_id> [limit]          # lists what would change
                       .venv/bin/python scripts/backfill_crm_names.py <user_id> [limit] --apply  # writes it

Reads whatever SUPABASE_URL points at (backend/.env is production). Only the memos of that user that are linked
to a HubSpot contact and are not being processed; only contactName, companyName and contactEmail of the
extraction, and only where the CRM has a value that differs from the one stored.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.deps import get_supabase  # noqa: E402
from app.services.crm_identity import crm_identity  # noqa: E402

IN_PROGRESS = ("uploading", "transcribing", "extracting", "pending_transcript")


async def main(user_id: str, limit: int, apply: bool) -> None:
    supabase = get_supabase()
    rows = (
        supabase.table("memos")
        .select("id,status,hubspot_contact_id,extraction")
        .eq("user_id", user_id)
        .not_.is_("hubspot_contact_id", "null")
        .not_.in_("status", list(IN_PROGRESS))
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )
    by_contact: dict[str, dict[str, str]] = {}
    changed = unchanged = unknown = 0
    for row in rows:
        contact_id = str(row["hubspot_contact_id"])
        if contact_id not in by_contact:
            by_contact[contact_id] = await crm_identity(supabase, user_id, contact_id)
        identity = by_contact[contact_id]
        extraction = row.get("extraction") if isinstance(row.get("extraction"), dict) else {}
        diff = {k: {"was": extraction.get(k), "now": v} for k, v in identity.items() if extraction.get(k) != v}
        if not identity:
            unknown += 1
        elif not diff:
            unchanged += 1
        else:
            changed += 1
            print(json.dumps({"memo_id": row["id"], "contact_id": contact_id, **diff}, ensure_ascii=False))
            if apply:
                supabase.table("memos").update({"extraction": {**extraction, **identity}}).eq("id", row["id"]).execute()
    print(
        json.dumps(
            {"memos": len(rows), "contacts": len(by_contact), "changed": changed, "unchanged": unchanged,
             "contact_not_found_in_crm": unknown, "applied": apply}
        )
    )


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--apply"]
    if not args:
        sys.exit(__doc__)
    asyncio.run(main(args[0], int(args[1]) if len(args) > 1 else 200, "--apply" in sys.argv))
