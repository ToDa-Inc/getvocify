"""Put one rep's HubSpot calls of one day right in Vocify. Dry run unless --apply.

For each call the rep made that day (their HubSpot owner), it says what it would do:
  ok              the call's memo is already the rep's (a failed one is retried as below)
  reassign        the call's memo is filed under someone else on the team (a manager's click): move it to the rep
  mark_no_answer  no memo and the call is under 30s: keep it as no answer, without transcribing it
  transcribe      no memo and the call is 30s or more: transcribe it, as the Transcribe button does
  no_recording    HubSpot has no recording for it: nothing to do

Usage (from backend/, with the production env):
  python scripts/backfill_crm_calls.py --email toni@getvocify.com --date 2026-10-28
  python scripts/backfill_crm_calls.py --email toni@getvocify.com --date 2026-10-28 --apply
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.hubspot.calls import (  # noqa: E402
    CALL_PROPERTIES,
    call_duration_seconds,
    is_short_call,
    parse_hubspot_timestamp_ms,
)


def plan_backfill(calls: list[dict], memos_by_call: dict[str, dict], rep_user_id: str) -> list[dict]:
    """One action per call, oldest first. `calls` are HubSpot call objects; `memos_by_call` the memo of each
    call that has one ({id, user_id})."""
    actions = []
    for call in calls:
        props = call.get("properties") or {}
        call_id = str(call.get("id"))
        memo = memos_by_call.get(call_id)
        if memo and str(memo.get("user_id")) != rep_user_id:
            action = "reassign"
        elif memo and memo.get("status") != "failed":
            action = "ok"
        elif not (props.get("hs_call_recording_url") or "").strip() and not is_short_call(props):
            action = "no_recording"
        else:
            # No memo, or the rep's memo failed (processing it again retries it).
            action = "mark_no_answer" if is_short_call(props) else "transcribe"
        actions.append({
            "action": action,
            "call_id": call_id,
            "at_ms": parse_hubspot_timestamp_ms(props.get("hs_timestamp")) or 0,
            "title": props.get("hs_call_title") or "",
            "seconds": call_duration_seconds(props),
            "memo_id": memo.get("id") if memo else None,
            "memo_user_id": str(memo.get("user_id")) if memo else None,
            "memo_status": memo.get("status") if memo else None,
        })
    return sorted(actions, key=lambda a: a["at_ms"])


def _user_id_for_email(supabase, email: str) -> Optional[str]:
    wanted = email.strip().lower()
    page = 1
    while True:
        users = supabase.auth.admin.list_users(page=page, per_page=200)
        for user in users:
            if (getattr(user, "email", "") or "").lower() == wanted:
                return str(user.id)
        if len(users) < 200:
            return None
        page += 1


async def _day_calls(client, owner_id: str, start: datetime, end: datetime) -> list[dict]:
    filters = [
        {"propertyName": "hubspot_owner_id", "operator": "EQ", "value": owner_id},
        {"propertyName": "hs_timestamp", "operator": "GTE", "value": str(int(start.timestamp() * 1000))},
        {"propertyName": "hs_timestamp", "operator": "LT", "value": str(int(end.timestamp() * 1000))},
    ]
    out, after = [], None
    while True:
        body = {
            "filterGroups": [{"filters": filters}],
            "sorts": [{"propertyName": "hs_timestamp", "direction": "ASCENDING"}],
            "properties": list(CALL_PROPERTIES),
            "limit": 100,
        }
        if after:
            body["after"] = after
        data = await client.post("/crm/v3/objects/calls/search", data=body) or {}
        out.extend(data.get("results") or [])
        after = ((data.get("paging") or {}).get("next") or {}).get("after")
        if not after:
            return out


async def _drain_background() -> None:
    """Transcription runs as tasks the request would have left running: wait for them before exiting."""
    while True:
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]
        if not pending:
            return
        await asyncio.gather(*pending, return_exceptions=True)


async def main(email: str, day: str, tz: str, apply: bool) -> None:
    from app.deps import get_supabase
    from app.services.company import CompanyService, get_company_id_for_user
    from app.services.company_scope import get_crm_connection
    from app.services.hubspot.call_processor import enqueue_hubspot_call_process
    from app.services.hubspot.client import HubSpotClient
    from app.services.hubspot.oauth import ensure_fresh_hubspot_connection
    from app.services.hubspot.sync import cache_owners_for_members

    supabase = get_supabase()
    rep = _user_id_for_email(supabase, email)
    if not rep:
        sys.exit(f"No Vocify user with email {email}")
    company_id = get_company_id_for_user(supabase, rep)
    conn = get_crm_connection(supabase, rep, "hubspot")
    if not company_id or not conn:
        sys.exit("The rep has no company or the company has no HubSpot connection")
    conn = ensure_fresh_hubspot_connection(supabase, conn)
    token = conn["access_token"]
    client = HubSpotClient(token)
    members = CompanyService(supabase).list_members(company_id)
    owner_id = (await cache_owners_for_members(client, supabase, conn["id"], members)).get(rep)
    if not owner_id:
        sys.exit(f"{email} matches no HubSpot owner")
    names = {m["user_id"]: m.get("full_name") or m.get("email") for m in members}

    zone = ZoneInfo(tz)
    start = datetime.combine(datetime.fromisoformat(day).date(), time.min, zone)
    calls = await _day_calls(client, str(owner_id), start, start + timedelta(days=1))
    ids = [str(c["id"]) for c in calls]
    memos = (
        supabase.table("memos").select("id,user_id,status,hubspot_engagement_id").in_("hubspot_engagement_id", ids).execute().data
        if ids else []
    ) or []
    plan = plan_backfill(calls, {str(m["hubspot_engagement_id"]): m for m in memos}, rep)

    print(f"{email} (HubSpot owner {owner_id}), {day} {tz}: {len(calls)} calls. {'APPLYING' if apply else 'DRY RUN'}")
    for a in plan:
        at = datetime.fromtimestamp(a["at_ms"] / 1000, zone).strftime("%H:%M") if a["at_ms"] else "--:--"
        who = (
            f"  memo {a['memo_id']} ({a['memo_status']}) of {names.get(a['memo_user_id'], a['memo_user_id'])}"
            if a["memo_id"] else ""
        )
        print(f"  {at}  {a['seconds']:>6.0f}s  {a['action']:<15} {a['call_id']}  {a['title']}{who}")
    counts: dict[str, int] = {}
    for a in plan:
        counts[a["action"]] = counts.get(a["action"], 0) + 1
    print("  " + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    if not apply:
        print("Nothing written. Run again with --apply.")
        return

    for a in plan:
        if a["action"] == "reassign":
            supabase.table("memos").update({"user_id": rep}).eq("id", a["memo_id"]).execute()
            supabase.table("action_signals").update({"user_id": rep}).eq("memo_id", a["memo_id"]).eq(
                "user_id", a["memo_user_id"]
            ).execute()
            print(f"  reassigned memo {a['memo_id']} to {email}")
        elif a["action"] in ("mark_no_answer", "transcribe"):
            result = await enqueue_hubspot_call_process(supabase, rep, a["call_id"], token)
            print(f"  {a['action']} {a['call_id']}: memo {result.get('memo_id')} ({result.get('status')})")
    await _drain_background()
    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True, help="the rep's Vocify email")
    parser.add_argument("--date", required=True, help="the day, YYYY-MM-DD")
    parser.add_argument("--tz", default="Europe/Madrid")
    parser.add_argument("--apply", action="store_true", help="write; without it nothing changes")
    args = parser.parse_args()
    asyncio.run(main(args.email, args.date, args.tz, args.apply))
