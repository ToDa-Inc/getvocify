"""General read-only HubSpot reporting for Ask.

Two primitives, `describe` and `run_query`, answer questions nobody wrote a tool for. They never guess:
property names and option values are checked against the portal's own schema, and a mistake comes back
as an error that lists the valid choices so the model can correct itself.

HubSpot's Search API returns an exact `total` for any filter, so counts and per-value breakdowns cost one
one-row search each. Sums and averages need the records, so they are computed over at most FETCH_CAP of
them and the result says when that is not everything. HubSpot has no join across objects: a question that
needs one is refused, not approximated.
"""

from __future__ import annotations

import asyncio
import difflib
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app.services.crm_copilot.crm_analytics import MAX_OWNERS, _ms, _owner_name, _owners, _pct, local_span, search
from app.services.hubspot.call_log import HUBSPOT_DISPOSITION_GUID

OBJECTS: dict[str, str] = {  # object type -> the date property a period applies to by default
    "contacts": "createdate",
    "companies": "createdate",
    "deals": "createdate",
    "calls": "hs_timestamp",
    "meetings": "hs_timestamp",
    "tasks": "hs_timestamp",
    "notes": "hs_timestamp",
}
OPERATORS = {"EQ", "NEQ", "GT", "GTE", "LT", "LTE", "IN", "NOT_IN", "HAS_PROPERTY", "NOT_HAS_PROPERTY", "CONTAINS_TOKEN"}
AGGREGATES = {"count", "sum", "avg", "min", "max"}
OWNER_PROPERTY = "hubspot_owner_id"
PAGE = 100
FETCH_CAP = 1000
MAX_CONDITIONS = 6  # HubSpot allows 6 conditions in one search: the period takes 2 and an owner scope 1
LOW_SAMPLE = 10  # a clock bucket with fewer records than this is flagged, not ranked
_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MAX_GROUPS = 25
COUNT_PER_OPTION_MAX = 20  # one exact count each; beyond this the records are tallied instead
MAX_BUCKETS = 24
MAX_REQUESTS = 60
CONCURRENCY = 4
LIST_MAX = 20
SCHEMA_TTL = 600.0
_SENSITIVE = {"sensitive", "highly_sensitive"}
_BODY_FIELDS = {"textarea", "html"}  # free text written by people or customers: never handed to the model as data
_BODY_NAMES = {"hs_note_body", "hs_call_body", "hs_meeting_body", "hs_task_body", "hs_body_preview", "hs_email_text", "hs_email_html"}
CELL_MAX = 120
_DISPOSITIONS = "/calling/v1/dispositions"
_KNOWN_DISPOSITION_LABELS = {"connected": "Connected", "voicemail": "Left voicemail", "busy": "Busy", "no_answer": "No answer"}

_schema_cache: dict[tuple, tuple[float, dict]] = {}


class QueryError(Exception):
    """A refusal the model can act on: `code` plus whatever detail helps it retry."""

    def __init__(self, code: str, **detail: Any) -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail

    def payload(self) -> dict:
        return {"ok": False, "error": self.code, **self.detail}


def _search_path(object_type: str) -> str:
    return f"/crm/v3/objects/{object_type}/search"


def _object(object_type: Any) -> str:
    name = str(object_type or "").strip().lower()
    if name not in OBJECTS:
        raise QueryError("unknown_object", object_type=name or None, valid=sorted(OBJECTS))
    return name


async def load_schema(client: Any, object_type: str, cache_key: str) -> dict[str, dict]:
    """name -> raw HubSpot property definition, cached briefly per connection."""
    key = (cache_key, object_type)
    hit = _schema_cache.get(key)
    if hit and time.monotonic() - hit[0] < SCHEMA_TTL:
        return hit[1]
    body = await client.get(f"/crm/v3/properties/{object_type}") or {}
    schema = {p["name"]: p for p in body.get("results") or [] if isinstance(p, dict) and p.get("name")}
    if schema:
        _schema_cache[key] = (time.monotonic(), schema)
    return schema


def clear_schema_cache() -> None:
    _schema_cache.clear()


def _prop(schema: dict[str, dict], name: Any) -> dict:
    wanted = str(name or "").strip()
    if wanted in schema:
        prop = schema[wanted]
    else:
        by_label = {str(p.get("label") or "").casefold(): p for p in schema.values()}
        prop = by_label.get(wanted.casefold())
        if prop is None:
            pool = list(schema) + [str(p.get("label")) for p in schema.values() if p.get("label")]
            close = difflib.get_close_matches(wanted, pool, n=6, cutoff=0.5)
            raise QueryError("unknown_property", property=wanted, did_you_mean=close, hint="call hubspot_describe with search=")
    if str(prop.get("dataSensitivity") or "").lower() in _SENSITIVE:
        raise QueryError("sensitive_property", property=prop["name"])
    return prop


async def _options(client: Any, object_type: str, prop: dict, cache_key: str) -> Optional[list[tuple[str, str]]]:
    """(value, label) pairs a filter or group can use, or None when the property is free-form."""
    name = prop["name"]
    if name == "hs_call_disposition":
        try:
            body = await client.get(_DISPOSITIONS)
            rows = body if isinstance(body, list) else (body or {}).get("results") or []
            found = [(str(r["id"]), str(r.get("label") or r["id"])) for r in rows if isinstance(r, dict) and r.get("id") and not r.get("deleted")]
        except Exception:  # noqa: BLE001 - the four confirmed outcomes are still true
            found = []
        return found or [(guid, _KNOWN_DISPOSITION_LABELS[key]) for key, guid in HUBSPOT_DISPOSITION_GUID.items()]
    if name == OWNER_PROPERTY:
        return [(str(o["id"]), _owner_name(o)) for o in (await _owners(client))[:MAX_OWNERS * 4]]
    if object_type == "deals" and name in ("dealstage", "pipeline"):
        body = await client.get("/crm/v3/pipelines/deals") or {}
        pipelines = [p for p in body.get("results") or [] if not p.get("archived")]
        if name == "pipeline":
            return [(str(p["id"]), str(p.get("label") or p["id"])) for p in pipelines]
        many = len(pipelines) > 1
        return [
            (str(s["id"]), f"{p.get('label')}: {s.get('label')}" if many else str(s.get("label") or s["id"]))
            for p in pipelines
            for s in p.get("stages") or []
        ]
    options = [(str(o["value"]), str(o.get("label") or o["value"])) for o in prop.get("options") or [] if isinstance(o, dict) and not o.get("hidden")]
    if not options and prop.get("type") == "bool":
        options = [("true", "Yes"), ("false", "No")]
    return options or None


def _match_option(options: list[tuple[str, str]], raw: Any, prop_name: str) -> str:
    text = str(raw).strip().casefold()
    for value, label in options:
        if text in (value.casefold(), label.casefold()):
            return value
    labels = [label for _, label in options]
    close = difflib.get_close_matches(str(raw), labels, n=5, cutoff=0.4)
    raise QueryError("unknown_option", property=prop_name, value=str(raw), options=labels[:40], did_you_mean=close)


def _to_ms(text: Any, prop_type: str, tz: ZoneInfo) -> str:
    try:
        day = datetime.fromisoformat(str(text).strip())
    except ValueError as exc:
        raise QueryError("bad_value", value=str(text), expected="an ISO date like 2026-08-31") from exc
    if prop_type == "date":
        return _ms(datetime(day.year, day.month, day.day, tzinfo=timezone.utc))
    return _ms(day if day.tzinfo else day.replace(tzinfo=tz))


_DURATION = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(ms|milliseconds?|s|secs?|seconds?|m|mins?|minutes?|h|hrs?|hours?)\s*$", re.I)
_UNIT_MS = {"ms": 1, "s": 1_000, "m": 60_000, "h": 3_600_000}


def _duration_ms(value: Any, prop_name: str) -> str:
    """HubSpot stores durations in milliseconds. A bare number is ambiguous (is 2 minutes '2', '120' or '120000'?),
    and a wrong guess filters silently, so the value must carry a unit."""
    match = _DURATION.match(str(value))
    if not match:
        raise QueryError("duration_needs_unit", property=prop_name, value=str(value), hint="write the unit: 2m, 90s, 1.5h or 120000ms")
    unit = match.group(2).lower()
    key = "ms" if unit.startswith("milli") or unit == "ms" else unit[0]
    return str(round(float(match.group(1).replace(",", ".")) * _UNIT_MS[key]))


def _number(value: Any, prop_name: str) -> str:
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError) as exc:
        raise QueryError("bad_value", property=prop_name, value=str(value), expected="a number") from exc
    return str(int(number)) if number.is_integer() else str(number)


async def _filter(client: Any, object_type: str, schema: dict, raw: Any, tz: ZoneInfo, cache_key: str, scoped: bool = False) -> tuple[dict, str]:
    if not isinstance(raw, dict):
        raise QueryError("bad_filter", expected="{property, operator, value|values}")
    prop = _prop(schema, raw.get("property"))
    name = prop["name"]
    if name == OWNER_PROPERTY and scoped:  # the scope is ANDed on anyway; a filter on it would only mislead ("nobody is unassigned")
        raise QueryError("use_user_id", hint="you can only see your own records here; owner is not a filter")
    op = str(raw.get("operator") or "EQ").upper()
    if op not in OPERATORS:
        raise QueryError("bad_operator", operator=op, valid=sorted(OPERATORS))
    label = str(prop.get("label") or name)
    if op in ("HAS_PROPERTY", "NOT_HAS_PROPERTY"):
        return {"propertyName": name, "operator": op}, f"{label} {'is set' if op == 'HAS_PROPERTY' else 'is empty'}"

    options = await _options(client, object_type, prop, cache_key) if prop.get("type") in ("enumeration", "bool") or name in ("hs_call_disposition", "dealstage", "pipeline") else None
    kind = str(prop.get("type") or "string")
    if options and op not in ("EQ", "NEQ", "IN", "NOT_IN"):
        raise QueryError("bad_operator_for_options", property=name, operator=op, valid=["EQ", "NEQ", "IN", "NOT_IN", "HAS_PROPERTY", "NOT_HAS_PROPERTY"])

    def coerce(value: Any) -> str:
        if options:
            return _match_option(options, value, name)
        if kind == "number" and _in_ms(prop):
            return _duration_ms(value, name)
        if kind == "number":
            return _number(value, name)
        if kind in ("date", "datetime"):
            return _to_ms(value, kind, tz)
        return str(value)

    if op in ("IN", "NOT_IN"):
        values = raw.get("values") if isinstance(raw.get("values"), list) else [raw.get("value")]
        values = [v for v in values if v not in (None, "")]
        if not values:
            raise QueryError("bad_filter", property=name, expected="values: [..]")
        flt = {"propertyName": name, "operator": op, "values": [coerce(v) for v in values]}
        return flt, f"{label} {'in' if op == 'IN' else 'not in'} {', '.join(str(v) for v in values)}"
    if raw.get("value") in (None, ""):
        raise QueryError("bad_filter", property=name, expected="value")
    shown = raw["value"]
    coerced = coerce(shown)
    readable = f" ({_human_ms(float(coerced))})" if kind == "number" and _in_ms(prop) else ""
    return {"propertyName": name, "operator": op, "value": coerced}, f"{label} {op.lower().replace('_', ' ')} {shown}{readable}"


def _period_filters(prop_name: str, start: datetime, end: datetime) -> list[dict]:
    return [
        {"propertyName": prop_name, "operator": "GTE", "value": _ms(start)},
        {"propertyName": prop_name, "operator": "LT", "value": _ms(end)},
    ]


class _Budget:
    def __init__(self) -> None:
        self.used = 0
        self.gate = asyncio.Semaphore(CONCURRENCY)

    async def post(self, client: Any, path: str, body: dict) -> dict:
        self.used += 1
        if self.used > MAX_REQUESTS:
            raise QueryError("too_broad", hint="narrow the period or the filters")
        async with self.gate:
            return await search(client, path, body)


async def _count(budget: _Budget, client: Any, object_type: str, filters: list[dict]) -> int:
    body = await budget.post(client, _search_path(object_type), {"filterGroups": [{"filters": filters}], "limit": 1, "properties": []})
    return int(body.get("total") or 0)


async def _fetch(budget: _Budget, client: Any, object_type: str, filters: list[dict], properties: list[str], want: int, sorts: Optional[list] = None) -> tuple[list[dict], int]:
    rows: list[dict] = []
    total = 0
    after = None
    while len(rows) < want:
        body = await budget.post(
            client,
            _search_path(object_type),
            {
                "filterGroups": [{"filters": filters}],
                "properties": properties,
                "limit": min(PAGE, want - len(rows)),
                **({"sorts": sorts} if sorts else {}),
                **({"after": after} if after else {}),
            },
        )
        total = int(body.get("total") or 0)
        rows += [r.get("properties") or {} for r in body.get("results") or []]
        after = ((body.get("paging") or {}).get("next") or {}).get("after")
        if not after:
            break
    return rows, total


def _readable(prop: dict) -> dict:
    """Properties whose values may be shown or grouped. Free-text bodies are not: other tools read notes."""
    if prop["name"] in _BODY_NAMES or str(prop.get("fieldType") or "").lower() in _BODY_FIELDS:
        raise QueryError("free_text_not_readable", property=prop["name"], hint="notes and messages are read with the notes tools, not hubspot_query")
    return prop


def _numeric(prop: dict, name: str) -> dict:
    if prop.get("type") != "number":
        raise QueryError("not_numeric", property=name, type=prop.get("type"))
    return prop


def _stats(values: list[float], aggregate: str) -> Optional[float]:
    if not values:
        return None
    result = {"sum": sum(values), "avg": sum(values) / len(values), "min": min(values), "max": max(values)}[aggregate]
    return round(result, 2)


def _describe_text(prop: dict) -> Optional[str]:
    text = " ".join(str(prop.get("description") or "").split())
    return text[:160] or None


def _in_ms(prop: dict) -> bool:
    return "millisecond" in str(prop.get("description") or "").lower()


def _human_ms(value: Optional[float]) -> Optional[str]:
    """HubSpot stores durations in milliseconds; the model gets a readable form it may quote as is."""
    if value is None:
        return None
    minutes, seconds = divmod(round(value / 1000), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m {seconds:02d}s"


def _as_float(raw: Any) -> Optional[float]:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _month_buckets(start: datetime, end: datetime, tz: ZoneInfo, bucket: str) -> list[tuple[str, datetime, datetime]]:
    local = start.astimezone(tz)
    if bucket == "month":
        cursor = datetime(local.year, local.month, 1, tzinfo=tz)
        step = lambda d: datetime(d.year + (d.month == 12), d.month % 12 + 1, 1, tzinfo=tz)  # noqa: E731
        name = lambda d: d.strftime("%Y-%m")  # noqa: E731
    elif bucket == "week":
        day = datetime(local.year, local.month, local.day, tzinfo=tz)
        cursor = day - timedelta(days=day.weekday())
        step = lambda d: (d + timedelta(days=7)).replace(tzinfo=tz)  # noqa: E731
        name = lambda d: f"week of {d.strftime('%Y-%m-%d')}"  # noqa: E731
    else:
        cursor = datetime(local.year, local.month, local.day, tzinfo=tz)
        step = lambda d: (d + timedelta(days=1)).replace(tzinfo=tz)  # noqa: E731
        name = lambda d: d.strftime("%Y-%m-%d")  # noqa: E731
    out = []
    while cursor.astimezone(timezone.utc) < end:
        nxt = step(cursor)
        out.append((name(cursor), max(cursor, start.astimezone(tz)), min(nxt, end.astimezone(tz))))
        cursor = nxt
    return out


async def _inline_options(client: Any, obj: str, props: list[dict], cache_key: str = "") -> dict[str, list[dict]]:
    """A search that lands on a few properties also shows their option values: one round trip fewer."""
    out: dict[str, list[dict]] = {}
    for prop in props:
        if prop.get("type") in ("enumeration", "bool") or prop["name"] in ("hs_call_disposition", "dealstage", "pipeline"):
            options = await _options(client, obj, prop, cache_key)
            if options and len(options) <= 25:
                out[prop["name"]] = [{"value": v, "label": l} for v, l in options]
    return out


async def describe(client: Any, object_type: Any, *, search: Optional[str], prop_name: Optional[str], cache_key: str) -> dict:
    """What can be asked: properties (with their real options) or one property in detail."""
    obj = _object(object_type)
    schema = await load_schema(client, obj, cache_key)
    if not schema:
        raise QueryError("schema_unavailable", object_type=obj)
    if prop_name:
        prop = _prop(schema, prop_name)
        options = await _options(client, obj, prop, cache_key) if prop.get("type") in ("enumeration", "bool") or prop["name"] in ("hs_call_disposition", "dealstage", "pipeline", OWNER_PROPERTY) else None
        return {
            "ok": True, "object": obj,
            "property": {
                "name": prop["name"], "label": prop.get("label"), "type": prop.get("type"), "description": _describe_text(prop),
                "options": [{"value": v, "label": l} for v, l in (options or [])[:60]] or None,
                "options_total": len(options or []),
            },
        }
    needle = str(search or "").strip().casefold()
    rows = [
        p for p in schema.values()
        if not p.get("hidden") and str(p.get("dataSensitivity") or "").lower() not in _SENSITIVE
        and (needle in p["name"].casefold() or needle in str(p.get("label") or "").casefold() if needle else not p.get("hubspotDefined"))
    ]
    rows.sort(key=lambda p: p["name"])
    inline = await _inline_options(client, obj, rows[:4]) if needle and len(rows) <= 4 else {}
    return {
        "ok": True, "object": obj, "matching": len(rows), "shown": min(len(rows), 40),
        "listing": "matches" if needle else "custom properties only; pass search= to find standard ones",
        "date_property_default": OBJECTS[obj],
        "properties": [
            {"name": p["name"], "label": p.get("label"), "type": p.get("type"), "description": _describe_text(p), **({"options": inline[p["name"]]} if p["name"] in inline else {})}
            for p in rows[:40]
        ],
    }


async def run_query(
    client: Any,
    *,
    object_type: Any,
    filters: Any,
    period: Optional[tuple[datetime, datetime]],
    date_property: Optional[str],
    owner_id: Optional[str],
    group_by: Optional[str],
    date_bucket: Optional[str],
    aggregate: str,
    metric_property: Optional[str],
    properties: Any,
    sort_by: Optional[str],
    sort_dir: Optional[str],
    limit: Any,
    tz_name: str,
    cache_key: str,
    share_where: Any = None,
    compare_previous: bool = False,
) -> dict:
    obj = _object(object_type)
    tz = ZoneInfo(tz_name or "UTC")
    schema = await load_schema(client, obj, cache_key)
    if not schema:
        raise QueryError("schema_unavailable", object_type=obj)
    user_filters = filters if isinstance(filters, list) else []
    aggregate = str(aggregate or "count").lower()
    if aggregate not in AGGREGATES:
        raise QueryError("bad_aggregate", valid=sorted(AGGREGATES))

    applied: list[str] = []
    hs_filters: list[dict] = []
    for raw in user_filters:
        flt, text = await _filter(client, obj, schema, raw, tz, cache_key, scoped=bool(owner_id))
        hs_filters.append(flt)
        applied.append(text)

    date_prop = _prop(schema, date_property or OBJECTS[obj])
    if date_prop.get("type") not in ("date", "datetime"):
        raise QueryError("not_a_date", property=date_prop["name"])
    core = list(hs_filters)
    if owner_id:
        core.append({"propertyName": OWNER_PROPERTY, "operator": "EQ", "value": str(owner_id)})
    base = [*core, *(_period_filters(date_prop["name"], *period) if period else [])]
    share_hs: list[dict] = []
    share_text: list[str] = []
    for raw in share_where if isinstance(share_where, list) else []:
        flt, text = await _filter(client, obj, schema, raw, tz, cache_key, scoped=bool(owner_id))
        share_hs.append(flt)
        share_text.append(text)
    if len(base) + len(share_hs) > MAX_CONDITIONS:
        raise QueryError("too_many_filters", max=MAX_CONDITIONS, hint="HubSpot allows 6 conditions per search, counting the period (2), share_where and a member's own-records scope (1)")

    budget = _Budget()
    out: dict[str, Any] = {
        "ok": True, "object": obj, "unit": obj, "applied": applied,
        "period": {**local_span(*period, tz_name or "UTC"), "property": date_prop["label"]} if period else None,
        "aggregate": aggregate,
    }
    metric = _numeric(_prop(schema, metric_property), metric_property) if aggregate != "count" and metric_property else None
    if aggregate != "count" and metric is None:
        raise QueryError("needs_metric_property", aggregate=aggregate)
    if aggregate == "count" and metric_property:
        raise QueryError("metric_needs_an_aggregate", property=metric_property, valid=["sum", "avg", "min", "max"])

    if properties or sort_by:  # list mode
        clashing = [name for name, given in (("group_by", group_by), ("date_bucket", date_bucket), ("share_where", share_hs), ("compare_previous", compare_previous), ("aggregate", aggregate != "count")) if given]
        if clashing:
            raise QueryError("list_mode_is_rows_only", ignored=clashing, hint="drop properties/sort_by for a count or breakdown, or drop these for a list")
        return await _list(budget, client, obj, schema, base, properties, sort_by, sort_dir, limit, cache_key, out, tz)

    if date_bucket:
        if date_bucket not in ("day", "week", "month", "hour", "weekday"):
            raise QueryError("bad_bucket", valid=["day", "week", "month", "hour", "weekday"])
        dated = _prop(schema, group_by) if group_by else date_prop  # a bucket with no group_by groups the object's own date
        if dated.get("type") not in ("date", "datetime"):
            raise QueryError("bucket_needs_a_date", property=dated["name"], hint="date_bucket groups by a date: drop group_by, or use a date property")
        if metric is not None:
            raise QueryError("bucket_needs_counts", hint="date_bucket gives counts and shares, not sum/avg")
        if date_bucket in ("hour", "weekday"):
            return await _by_clock(budget, client, obj, base, dated, date_bucket, share_hs, share_text, tz, out)
        return await _by_bucket(budget, client, obj, core, dated["name"], date_bucket, period, tz, schema, out, share_hs, share_text)
    if compare_previous and (group_by or not period):
        raise QueryError("compare_needs_period", hint="compare_previous needs a period and no group_by")
    if share_hs and metric is not None:
        raise QueryError("share_needs_counts", hint="share_where works with counts, not with sum/avg")

    total = await _count(budget, client, obj, base)
    out["n"] = total
    if not group_by:
        if metric is None:
            out.update(coverage="complete", n_analysed=total, value=total)
            if share_hs:
                out["share"] = _share(await _count(budget, client, obj, [*base, *share_hs]), total, share_text)
        else:
            values, rows_total = await _values(budget, client, obj, base, metric["name"], total)
            out.update(_metric_block(metric, aggregate, values, total, rows_total))
        if compare_previous:
            out["previous"] = await _previous(budget, client, obj, core, date_prop["name"], period, share_hs, share_text, metric, aggregate, out, tz)
        return out

    gprop = _readable(_prop(schema, group_by))
    options = await _options(client, obj, gprop, cache_key) if gprop.get("type") in ("enumeration", "bool") or gprop["name"] in ("hs_call_disposition", "dealstage", "pipeline", OWNER_PROPERTY) else None
    out["group_by"] = gprop.get("label") or gprop["name"]
    if options and metric is None and len(options) <= COUNT_PER_OPTION_MAX:
        each = [[*base, {"propertyName": gprop["name"], "operator": "EQ", "value": value}] for value, _ in options]
        counts = await asyncio.gather(*(_count(budget, client, obj, f) for f in each))
        matching = await asyncio.gather(*(_count(budget, client, obj, [*f, *share_hs]) if share_hs and c else _zero() for f, c in zip(each, counts)))
        groups = [
            {"key": label, "count": c, "share_pct": _pct(c, total), **({"matching": m, "matching_pct": _pct(m, c)} if share_hs else {})}
            for (_, label), c, m in zip(options, counts, matching) if c
        ]
        if share_hs:  # over every record, not just the listed groups
            out["share"] = _share(await _count(budget, client, obj, [*base, *share_hs]), total, share_text)
        other = max(total - sum(c for c in counts), 0)
        groups.sort(key=lambda g: (-g["count"], str(g["key"]).casefold()))
        out.update(groups=groups[:MAX_GROUPS], not_in_listed_groups=other, coverage="complete", n_analysed=total, truncated=len(groups) > MAX_GROUPS)
        return out
    if share_hs:
        raise QueryError("share_needs_countable_groups", hint="group by an option property such as owner, stage or outcome")
    return await _tally(budget, client, obj, base, gprop, options, metric, aggregate, total, out)


async def _zero() -> int:
    return 0


def _share(matching: int, total: int, condition: list[str]) -> dict:
    return {"matching": matching, "of": total, "pct": _pct(matching, total), "condition": " and ".join(condition)}


def _change_pct(now: Optional[float], before: Optional[float]) -> Optional[float]:
    if now is None or before in (None, 0):
        return None
    return round((now - before) * 100 / before, 1)


def _previous_window(start: datetime, end: datetime, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """A calendar month is compared with the calendar month before it; any other window with the equal span before it."""
    first, after = start.astimezone(tz), end.astimezone(tz)
    if first.day == after.day == 1 and first.time() == after.time() == datetime.min.time() and (after.year, after.month) == ((first.year + (first.month == 12)), first.month % 12 + 1):
        before = datetime(first.year - (first.month == 1), (first.month - 2) % 12 + 1, 1, tzinfo=tz)
        return before.astimezone(timezone.utc), start
    return start - (end - start), start


async def _previous(budget, client, obj, core, date_name, period, share_hs, share_text, metric, aggregate, current, tz) -> dict:
    """The same question over the window just before, so 'vs last month' is computed here, not by the model."""
    window = _previous_window(*period, tz)
    base = [*core, *_period_filters(date_name, *window)]
    total = await _count(budget, client, obj, base)
    block: dict[str, Any] = {"period": local_span(*window, tz.key), "n": total, "change_n_pct": _change_pct(current["n"], total)}
    if metric is None:
        block["value"] = total
        if share_hs:
            block["share"] = _share(await _count(budget, client, obj, [*base, *share_hs]), total, share_text)
            now = (current.get("share") or {}).get("pct")
            block["change_share_pts"] = round(now - block["share"]["pct"], 1) if now is not None and block["share"]["pct"] is not None else None
    else:
        values, _ = await _values(budget, client, obj, base, metric["name"], total)
        block["value"] = _stats(values, aggregate)
        block["change_value_pct"] = _change_pct(current.get("value"), block["value"])
    return block


def _matches(row: dict, flt: dict) -> bool:
    """The HubSpot filters above, evaluated on a fetched record (used where HubSpot cannot group)."""
    have, op = row.get(flt["propertyName"]), flt["operator"]
    if op == "HAS_PROPERTY":
        return have not in (None, "")
    if op == "NOT_HAS_PROPERTY":
        return have in (None, "")
    if op in ("IN", "NOT_IN"):
        inside = str(have).casefold() in {str(v).casefold() for v in flt.get("values") or []}
        return inside if op == "IN" else not inside
    if have in (None, ""):
        return False
    want = flt.get("value")
    a, b = _as_float(have), _as_float(want)
    if op in ("GT", "GTE", "LT", "LTE") and a is not None and b is not None:
        return {"GT": a > b, "GTE": a >= b, "LT": a < b, "LTE": a <= b}[op]
    if op == "EQ":
        return str(have).casefold() == str(want).casefold()
    if op == "NEQ":
        return str(have).casefold() != str(want).casefold()
    return op == "CONTAINS_TOKEN" and str(want).casefold() in str(have).casefold()


async def _by_clock(budget, client, obj, base, gprop, bucket, share_hs, share_text, tz, out) -> dict:
    """Hour of day or weekday. HubSpot cannot group by either, so the most recent records are bucketed here."""
    if gprop.get("type") not in ("date", "datetime"):
        raise QueryError("not_a_date", property=gprop["name"])
    fields = [gprop["name"], *dict.fromkeys(f["propertyName"] for f in share_hs)]
    rows, total = await _fetch(budget, client, obj, base, fields, FETCH_CAP, [{"propertyName": gprop["name"], "direction": "DESCENDING"}])
    seen: dict[int, list[int]] = {}
    for row in rows:
        stamp = _as_float(row.get(gprop["name"]))
        if stamp is None:
            continue
        local = datetime.fromtimestamp(stamp / 1000, tz)
        key = local.hour if bucket == "hour" else local.weekday()
        cell = seen.setdefault(key, [0, 0])
        cell[0] += 1
        cell[1] += bool(share_hs) and all(_matches(row, f) for f in share_hs)
    counted = sum(c[0] for c in seen.values())
    groups = []
    for key in sorted(seen):
        count, hit = seen[key]
        item = {"key": f"{key:02d}:00-{key:02d}:59" if bucket == "hour" else _WEEKDAYS[key], "count": count, "share_pct": _pct(count, counted)}
        if share_hs:
            item.update(matching=hit, matching_pct=_pct(hit, count), low_sample=count < LOW_SAMPLE)
        groups.append(item)
    complete = len(rows) >= total
    out.update(
        n=total, n_analysed=len(rows), coverage="complete" if complete else "partial", group_by=f"{gprop.get('label') or gprop['name']} by {bucket}", groups=groups,
        **({"share": _share(sum(c[1] for c in seen.values()), counted, share_text)} if share_hs else {}),
        **({} if complete else {"note": f"the most recent {len(rows)} of {total} records"}),
    )
    return out


async def _values(budget: _Budget, client: Any, obj: str, base: list[dict], prop_name: str, total: int) -> tuple[list[float], int]:
    rows, _ = await _fetch(budget, client, obj, base, [prop_name], min(total, FETCH_CAP))
    return [v for v in (_as_float(r.get(prop_name)) for r in rows) if v is not None], len(rows)


def _metric_block(metric: dict, aggregate: str, values: list[float], total: int, fetched: int) -> dict:
    complete = fetched >= total
    value = _stats(values, aggregate)
    return {
        "metric": metric.get("label") or metric["name"], "value": value, **({"value_readable": _human_ms(value)} if _in_ms(metric) else {}), "n_with_value": len(values),
        "n": total, "n_analysed": fetched, "coverage": "complete" if complete else "partial",
        "note": "values as stored in HubSpot, no currency conversion" + ("" if complete else f"; computed over the first {fetched} of {total}"),
    }


async def _tally(budget, client, obj, base, gprop, options, metric, aggregate, total, out) -> dict:
    labels = dict(options or [])
    fields = [gprop["name"], *([metric["name"]] if metric else [])]
    rows, _ = await _fetch(budget, client, obj, base, fields, min(total, FETCH_CAP))
    buckets: dict[str, list[float]] = {}
    counts: dict[str, int] = {}
    unset = 0
    for row in rows:
        raw = str(row.get(gprop["name"]) or "").strip()
        if not raw:
            unset += 1
            continue
        for part in (raw.split(";") if gprop.get("type") == "enumeration" and gprop.get("fieldType") == "checkbox" else [raw]):
            key = labels.get(part.strip(), part.strip())
            counts[key] = counts.get(key, 0) + 1
            if metric:
                value = _as_float(row.get(metric["name"]))
                if value is not None:
                    buckets.setdefault(key, []).append(value)
    groups = []
    for key, count in counts.items():
        item = {"key": key, "count": count, "share_pct": _pct(count, len(rows))}
        if metric:
            item[aggregate] = _stats(buckets.get(key, []), aggregate)
            if _in_ms(metric):
                item[f"{aggregate}_readable"] = _human_ms(item[aggregate])
        groups.append(item)
    groups.sort(key=lambda g: (-g["count"], g["key"].casefold()))
    complete = len(rows) >= total
    out.update(
        groups=groups[:MAX_GROUPS], truncated=len(groups) > MAX_GROUPS, no_value=unset, n_analysed=len(rows),
        coverage="complete" if complete else "partial", metric=(metric.get("label") or metric["name"]) if metric else None,
    )
    if not complete:
        out["note"] = f"grouped over the first {len(rows)} of {total}, not the whole set"
    return out


async def _by_bucket(budget, client, obj, core, group_by, bucket, period, tz, schema, out, share_hs, share_text) -> dict:
    if not period:
        raise QueryError("bucket_needs_period")
    gprop = schema[group_by]
    windows = _month_buckets(period[0], period[1], tz, bucket)
    if bucket != "month":  # name a bucket by the days it really covers: the first and last can be partial
        windows = [(f"{s.strftime('%Y-%m-%d')} to {(e - timedelta(days=1)).strftime('%Y-%m-%d')}" if bucket == "week" else s.strftime("%Y-%m-%d"), s, e) for _, s, e in windows]
    if len(windows) > MAX_BUCKETS:
        raise QueryError("too_many_buckets", max=MAX_BUCKETS, hint="a coarser bucket or a shorter period")
    each = [[*core, *_period_filters(gprop["name"], s, e)] for _, s, e in windows]
    counts = await asyncio.gather(*(_count(budget, client, obj, f) for f in each))
    matching = await asyncio.gather(*(_count(budget, client, obj, [*f, *share_hs]) if share_hs and c else _zero() for f, c in zip(each, counts)))
    total = sum(counts)
    out.update(
        n=total, n_analysed=total, coverage="complete", group_by=f"{gprop.get('label') or gprop['name']} by {bucket}",
        groups=[
            {"key": name, "count": c, "share_pct": _pct(c, total), **({"matching": m, "matching_pct": _pct(m, c), "low_sample": c < LOW_SAMPLE} if share_hs else {})}
            for (name, _, _), c, m in zip(windows, counts, matching)
        ],
        **({"share": _share(sum(matching), total, share_text)} if share_hs else {}),
    )
    return out


async def _list(budget, client, obj, schema, base, properties, sort_by, sort_dir, limit, cache_key, out, tz) -> dict:
    names = [_readable(_prop(schema, p))["name"] for p in (properties if isinstance(properties, list) else [])[:8]]
    if not names:
        raise QueryError("needs_properties", hint="list mode needs properties: [..]")
    sorts = None
    if sort_by:
        sorts = [{"propertyName": _prop(schema, sort_by)["name"], "direction": "ASCENDING" if str(sort_dir or "").lower().startswith("asc") else "DESCENDING"}]
    want = max(1, min(int(limit or 10), LIST_MAX))
    rows, total = await _fetch(budget, client, obj, base, names, want, sorts)
    lookups: dict[str, dict[str, str]] = {}
    for name in names:
        prop = schema[name]
        if prop.get("type") in ("enumeration", "bool") or name in ("hs_call_disposition", "dealstage", "pipeline", OWNER_PROPERTY):
            options = await _options(client, obj, prop, cache_key)
            if options:
                lookups[name] = dict(options)
    def cell(name: str, raw: Any) -> Any:
        if _in_ms(schema[name]) and _as_float(raw) is not None:
            return _human_ms(_as_float(raw))
        if schema[name].get("type") in ("date", "datetime") and _as_float(raw) is not None:
            return datetime.fromtimestamp(_as_float(raw) / 1000, tz).strftime("%Y-%m-%d")
        value = lookups.get(name, {}).get(str(raw), raw)
        return value[:CELL_MAX] if isinstance(value, str) else value

    shown = [{schema[n].get("label") or n: cell(n, r.get(n)) for n in names} for r in rows]
    out.update(n=total, n_analysed=total, coverage="complete", rows=shown, mode="list", shown=len(shown))
    return out
