"""HubSpot analytics for Ask: counts and rates from the CRM itself, not from Vocify's captures.

HubSpot's Search API returns an exact `total` for any filter, so a rate is a few one-row searches
instead of a download. Nothing here guesses: a call with no logged outcome is reported as unknown,
and a portal with no lost-reason property gets counts but no invented reasons.
"""

from __future__ import annotations

import asyncio
import time
import weakref
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app.services.hubspot.call_log import HUBSPOT_DISPOSITION_GUID
from app.services.hubspot.exceptions import HubSpotRateLimitError

# HubSpot's search endpoints allow about five requests a second per account and answer 429 without a retryAfter,
# which the client does not retry. Ask fires several searches per question, so they are spaced and a 429 is retried.
SEARCH_INTERVAL = 0.25
SEARCH_RETRIES = 3
RETRY_BACKOFF = 1.0  # seconds, times the attempt number, when HubSpot gives no retryAfter
_pacers: "weakref.WeakKeyDictionary[Any, _Pacer]" = weakref.WeakKeyDictionary()


class _Pacer:
    def __init__(self) -> None:
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            delay = self._next - now
            if delay > 0:
                await asyncio.sleep(delay)
            self._next = max(now, self._next) + SEARCH_INTERVAL


async def search(client: Any, path: str, body: dict) -> dict:
    """One HubSpot search, paced per client and retried when HubSpot says slow down."""
    pacer = _pacers.setdefault(client, _Pacer())
    for attempt in range(SEARCH_RETRIES + 1):
        await pacer.wait()
        try:
            return await client.post(path, body) or {}
        except HubSpotRateLimitError as exc:
            if attempt == SEARCH_RETRIES:
                raise
            await asyncio.sleep(min(float(exc.retry_after or RETRY_BACKOFF * (1 + attempt)), 5.0))
    return {}

MAX_SPAN_DAYS = 366
MAX_OWNERS = 15
PAGE = 100
_CALLS = "/crm/v3/objects/calls/search"
_DEALS = "/crm/v3/objects/deals/search"
# The four outcomes whose GUIDs the repo already confirms (call_log.HUBSPOT_DISPOSITION_GUID).
_OUTCOMES = ("connected", "voicemail", "no_answer", "busy")


def resolve_period(args: dict, tz_name: str, max_days: int = MAX_SPAN_DAYS) -> tuple[datetime, datetime]:
    """[start, end) in UTC. `month`, `start_date`+`end_date` (inclusive) or `period_days`."""
    tz = ZoneInfo(tz_name or "UTC")
    month = str(args.get("month") or "").strip()
    if month:
        try:
            year, mon = (int(part) for part in month.split("-"))
            first = datetime(year, mon, 1, tzinfo=tz)
        except (ValueError, TypeError) as exc:
            raise ValueError("month must look like 2026-08") from exc
        nxt = datetime(year + (mon == 12), mon % 12 + 1, 1, tzinfo=tz)
        start, end = first, nxt
    elif args.get("start_date"):
        try:
            first = datetime.fromisoformat(str(args["start_date"])).replace(tzinfo=tz)
            last = datetime.fromisoformat(str(args.get("end_date") or args["start_date"])).replace(tzinfo=tz)
        except ValueError as exc:
            raise ValueError("dates must look like 2026-08-31") from exc
        start, end = first, last + timedelta(days=1)
    elif args.get("period_days"):
        days = int(args["period_days"])
        if days < 1:
            raise ValueError("period_days must be positive")
        end_now = datetime.now(timezone.utc)
        start, end = end_now - timedelta(days=days), end_now
    else:
        raise ValueError("give month, start_date and end_date, or period_days")
    if end <= start:
        raise ValueError("the period ends before it starts")
    if (end - start).days > max_days:
        raise ValueError("the period is longer than a year" if max_days == MAX_SPAN_DAYS else "the period is too long")
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def local_span(start: datetime, end: datetime, tz_name: str) -> dict:
    """[start, end) as the calendar days the account sees, inclusive: what a person (and a model) can quote."""
    tz = ZoneInfo(tz_name or "UTC")
    return {"from": start.astimezone(tz).date().isoformat(), "to": (end.astimezone(tz) - timedelta(seconds=1)).date().isoformat()}


def _ms(moment: datetime) -> str:
    return str(int(moment.timestamp() * 1000))


def _call_filters(start: datetime, end: datetime, direction: Optional[str], owner_id: Optional[str]) -> list[dict]:
    filters = [
        {"propertyName": "hs_timestamp", "operator": "GTE", "value": _ms(start)},
        {"propertyName": "hs_timestamp", "operator": "LT", "value": _ms(end)},
    ]
    if direction:
        filters.append({"propertyName": "hs_call_direction", "operator": "EQ", "value": direction.upper()})
    if owner_id:
        filters.append({"propertyName": "hubspot_owner_id", "operator": "EQ", "value": str(owner_id)})
    return filters


async def _count(client: Any, path: str, filters: list[dict]) -> int:
    body = await search(client, path, {"filterGroups": [{"filters": filters}], "limit": 1, "properties": []})
    return int(body.get("total") or 0)


def _pct(part: int, whole: int) -> Optional[float]:
    return round(part * 100 / whole, 1) if whole else None


async def call_stats(
    client: Any,
    *,
    start: datetime,
    end: datetime,
    direction: Optional[str] = "OUTBOUND",
    owner_id: Optional[str] = None,
) -> dict:
    base = _call_filters(start, end, direction, owner_id)
    disposition = lambda key: [  # noqa: E731
        *base,
        {"propertyName": "hs_call_disposition", "operator": "EQ", "value": HUBSPOT_DISPOSITION_GUID[key]},
    ]
    counts = await asyncio.gather(
        _count(client, _CALLS, base), *(_count(client, _CALLS, disposition(k)) for k in _OUTCOMES)
    )
    total, by_outcome = counts[0], dict(zip(_OUTCOMES, counts[1:]))
    unknown = max(total - sum(by_outcome.values()), 0)
    return {
        "total": total,
        **by_outcome,
        "outcome_unknown": unknown,
        "outcome_known_pct": _pct(total - unknown, total),
        "connection_rate_pct": _pct(by_outcome["connected"], total),
        "direction": direction.lower() if direction else "all",
    }


async def _owners(client: Any) -> list[dict]:
    owners: list[dict] = []
    after = None
    while len(owners) < 200:
        params = {"limit": 100, **({"after": after} if after else {})}
        body = await client.get("/crm/v3/owners", params=params) or {}
        owners += body.get("results") or []
        after = ((body.get("paging") or {}).get("next") or {}).get("after")
        if not after:
            break
    return owners


def _owner_name(owner: dict) -> str:
    name = f"{owner.get('firstName') or ''} {owner.get('lastName') or ''}".strip()
    return name or str(owner.get("email") or owner.get("id"))


async def call_stats_by_owner(
    client: Any, *, start: datetime, end: datetime, direction: Optional[str] = "OUTBOUND"
) -> list[dict]:
    """One row per rep with calls in the period. Alphabetical: this is a breakdown, not a ranking."""
    owners = (await _owners(client))[:MAX_OWNERS]

    async def row(owner: dict) -> Optional[dict]:
        base = _call_filters(start, end, direction, owner["id"])
        total, connected = await asyncio.gather(
            _count(client, _CALLS, base),
            _count(client, _CALLS, [*base, {"propertyName": "hs_call_disposition", "operator": "EQ", "value": HUBSPOT_DISPOSITION_GUID["connected"]}]),
        )
        if not total:
            return None
        return {"rep": _owner_name(owner), "total": total, "connected": connected, "connection_rate_pct": _pct(connected, total)}

    rows = [r for r in await asyncio.gather(*(row(o) for o in owners)) if r]
    return sorted(rows, key=lambda r: r["rep"].casefold())


async def lost_reasons(
    client: Any,
    schema_service: Any,
    *,
    start: datetime,
    end: datetime,
    top_n: int = 5,
    owner_id: Optional[str] = None,
    configured_property: Optional[str] = None,
    max_fetch: int = 500,
) -> dict:
    from app.services.hubspot.call_outcome import resolve_lost_reason_property

    def window(flag: str) -> list[dict]:
        filters = [
            {"propertyName": "closedate", "operator": "GTE", "value": _ms(start)},
            {"propertyName": "closedate", "operator": "LT", "value": _ms(end)},
            {"propertyName": flag, "operator": "EQ", "value": "true"},
        ]
        if owner_id:
            filters.append({"propertyName": "hubspot_owner_id", "operator": "EQ", "value": str(owner_id)})
        return filters

    prop = await resolve_lost_reason_property(schema_service, configured_property)
    lost, won = await asyncio.gather(
        _count(client, _DEALS, window("hs_is_closed_lost")), _count(client, _DEALS, window("hs_is_closed_won"))
    )
    out: dict = {
        "lost": lost,
        "won": won,
        "win_rate_pct": _pct(won, won + lost),
        "reason_property": prop.label if prop else None,
        "reasons": None,
        "no_reason": None,
        "fetched": 0,
    }
    if not prop or not lost:
        return out
    labels = {o.value: o.label for o in prop.options}
    counts: dict[str, int] = {}
    fetched = no_reason = 0
    after = None
    want = min(lost, max_fetch)
    while fetched < want:
        body = await search(
            client,
            _DEALS,
            {
                "filterGroups": [{"filters": window("hs_is_closed_lost")}],
                "properties": [prop.name],
                "limit": min(PAGE, want - fetched),
                **({"after": after} if after else {}),
            },
        )
        for item in body.get("results") or []:
            fetched += 1
            raw = str((item.get("properties") or {}).get(prop.name) or "").strip()
            if not raw:
                no_reason += 1
                continue
            for value in raw.split(";"):
                label = labels.get(value.strip(), value.strip())
                counts[label] = counts.get(label, 0) + 1
        after = ((body.get("paging") or {}).get("next") or {}).get("after")
        if not after:
            break
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].casefold()))[:top_n]
    out["reasons"] = [{"reason": name, "count": n, "share_pct": _pct(n, fetched)} for name, n in ranked]
    out["no_reason"] = no_reason
    out["fetched"] = fetched
    return out
