"""Tie a desktop call recording to the call HubSpot logs for it.

The desktop records the call itself (live transcript, memo ready at hang-up).
The dialer then logs the same call in HubSpot, which the extension and the
recording webhook would otherwise transcribe again. Linking sets the memo's
hubspot_engagement_id, which every HubSpot call path already treats as
"this call has a memo": the recordings list shows it, processing reuses it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from supabase import Client

logger = logging.getLogger(__name__)

# HubSpot's hs_timestamp is when the dialer started or logged the call; the
# desktop capture starts within seconds of it. Redials are usually further apart.
LINK_WINDOW_SECONDS = 5 * 60
# Two candidates whose scores are this close are a coin flip: link neither.
AMBIGUITY_SECONDS = 20
CANDIDATE_LOOKBACK_HOURS = 24


def _epoch_seconds(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def match_calls_to_memos(calls: Iterable[dict], memos: Iterable[dict]) -> dict[str, str]:
    """{hubspot call id: memo id} for pairs that clearly belong together.

    calls: {call_id, timestamp_ms, duration_ms}. memos: {id, capture_started_at,
    audio_duration (s)}. A pair needs start times within LINK_WINDOW_SECONDS;
    the score adds the duration gap so an answered call beats a short no-answer
    redial. Best pairs win first, each side is used once, and a near-tie on
    either side links nothing.
    """
    pairs: list[tuple[float, str, str]] = []
    for call in calls:
        call_id = str(call.get("call_id") or "")
        start_ms = call.get("timestamp_ms")
        if not call_id or start_ms is None:
            continue
        call_start = float(start_ms) / 1000
        call_duration = float(call.get("duration_ms") or 0) / 1000
        for memo in memos:
            memo_id = str(memo.get("id") or "")
            memo_start = _epoch_seconds(memo.get("capture_started_at"))
            if not memo_id or memo_start is None:
                continue
            gap = abs(call_start - memo_start)
            if gap > LINK_WINDOW_SECONDS:
                continue
            memo_duration = float(memo.get("audio_duration") or 0)
            # A no-answer attempt (0 s) must lose to the answered call when the
            # memo is long; an unknown memo duration compares on start only.
            duration_gap = abs(call_duration - memo_duration) if memo_duration else 0.0
            pairs.append((gap + duration_gap, call_id, memo_id))

    pairs.sort()
    links: dict[str, str] = {}
    used_memos: set[str] = set()
    for score, call_id, memo_id in pairs:
        if call_id in links or memo_id in used_memos:
            continue
        # Another still-open pairing for this call or this memo, nearly as good.
        contested = any(
            (c == call_id) != (m == memo_id)
            and c not in links
            and m not in used_memos
            and other - score < AMBIGUITY_SECONDS
            for other, c, m in pairs
        )
        if contested:
            continue
        links[call_id] = memo_id
        used_memos.add(memo_id)
    return links


def unlinked_desktop_call_memos(
    supabase: Client,
    user_id: str,
    contact_ids: list[str],
) -> list[dict]:
    """The rep's recent, finished desktop call captures on these contacts not yet tied to a HubSpot call.

    A capture still recording is left out: if the desktop app died mid-call it
    never finishes, and HubSpot's recording must then be processed as usual.
    """
    if not contact_ids:
        return []
    since = (datetime.now(timezone.utc) - timedelta(hours=CANDIDATE_LOOKBACK_HOURS)).isoformat()
    result = (
        supabase.table("memos")
        .select("id,capture_started_at,audio_duration,hubspot_contact_id")
        .eq("user_id", user_id)
        .eq("source", "desktop")
        .eq("interaction_kind", "call")
        .in_("hubspot_contact_id", contact_ids)
        .is_("hubspot_engagement_id", "null")
        .neq("capture_status", "recording")
        .gte("capture_started_at", since)
        .execute()
    )
    return list(result.data or [])


def _calls_with_memos(supabase: Client, call_ids: list[str]) -> set[str]:
    if not call_ids:
        return set()
    result = (
        supabase.table("memos")
        .select("hubspot_engagement_id")
        .in_("hubspot_engagement_id", call_ids)
        .execute()
    )
    return {str(row["hubspot_engagement_id"]) for row in result.data or [] if row.get("hubspot_engagement_id")}


def link_memos(supabase: Client, links: dict[str, str]) -> dict[str, str]:
    """Write each link; one that lost a race (memo or call already linked) is skipped."""
    done: dict[str, str] = {}
    for call_id, memo_id in links.items():
        try:
            updated = (
                supabase.table("memos")
                .update({"hubspot_engagement_id": call_id})
                .eq("id", memo_id)
                .is_("hubspot_engagement_id", "null")
                .execute()
            )
        except Exception as e:
            # Unique index on hubspot_engagement_id: another memo owns this call.
            logger.info("Desktop memo %s not linked to HubSpot call %s: %s", memo_id, call_id, e)
            continue
        if updated.data:
            done[call_id] = memo_id
    return done


def link_desktop_calls_for_contact(
    supabase: Client,
    user_id: str,
    contact_id: str,
    calls: list[dict],
    already_linked: Iterable[str] = (),
) -> dict[str, str]:
    """Link HubSpot calls listed on a contact to the rep's desktop recordings of them."""
    taken = {str(c) for c in already_linked}
    open_calls = [c for c in calls if str(c.get("call_id")) not in taken]
    if not open_calls:
        return {}
    try:
        memos = unlinked_desktop_call_memos(supabase, user_id, [str(contact_id)])
        if not memos:
            return {}
        taken |= _calls_with_memos(supabase, [str(c["call_id"]) for c in open_calls])
        open_calls = [c for c in open_calls if str(c.get("call_id")) not in taken]
    except Exception as e:
        logger.warning("Desktop call linking skipped: %s", e)
        return {}
    return link_memos(supabase, match_calls_to_memos(open_calls, memos))


def link_desktop_call(
    supabase: Client,
    user_id: str,
    call: dict,
    contact_ids: list[str],
) -> Optional[str]:
    """The desktop memo for this one HubSpot call, now linked, or None."""
    try:
        memos = unlinked_desktop_call_memos(supabase, user_id, [str(c) for c in contact_ids])
        if not memos:
            return None
        return link_memos(supabase, match_calls_to_memos([call], memos)).get(str(call.get("call_id")))
    except Exception as e:
        logger.warning("Desktop call linking skipped: %s", e)
        return None
