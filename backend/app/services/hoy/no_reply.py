"""Hoy «no te ha respondido»: the rep's last email to a contact, unanswered for ten local days. No model call."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from app.services.crm_providers.coverage import read_envelope
from app.services.hoy.assigned import _ReadFailed, _call, _owner_emails
from app.services.hoy.materialize import _commitments, _intelligence, day_end
from app.services.hoy.reconcile import plan_reconcile
from app.services.hoy.signals import COLD_AFTER, Signal

logger = logging.getLogger(__name__)

NO_REPLY_FLAG = "HOY_NO_REPLY_ENABLED"
NO_REPLY_AFTER_DAYS = COLD_AFTER.days
NO_REPLY_LOOKBACK_DAYS = 30
DEFAULT_TZ = "Europe/Madrid"

_BATCH = 100
_MEMO_CHUNK = 200
_MAX_PAGES = 10
_MAX_CANDIDATES = 200
_MAX_OBJECTS = 2000
_CONVERSATION = frozenset({"email_in", "call", "meeting", "memo"})
_SENT_STATUSES = frozenset({"", "SENT"})
_OUTGOING = frozenset({"EMAIL", "FORWARDED_EMAIL"})
_ENGAGEMENTS = ("emails", "calls", "meetings")
_PROPERTIES = {
    "emails": ["hs_timestamp", "hs_email_direction", "hs_email_subject", "hubspot_owner_id", "hs_email_status"],
    "calls": ["hs_timestamp"],
    "meetings": ["hs_timestamp"],
}
_ENGAGEMENT_KIND = {"calls": "call", "meetings": "meeting"}

ActivityKind = Literal["email_out", "email_in", "call", "meeting", "memo"]


@dataclass(frozen=True)
class Activity:
    kind: ActivityKind
    at: datetime
    id: str = ""
    subject: Optional[str] = None
    by_rep: bool = False


def _local_date(value: datetime, tz_name: str | None):
    return value.astimezone(ZoneInfo(tz_name or DEFAULT_TZ)).date()


def no_reply_signal(
    contact_id: str,
    activities: list[Activity],
    *,
    now: datetime,
    tz_name: str | None,
    connection_id: Optional[str] = None,
    future_commitment: bool = False,
    contact_name: Optional[str] = None,
) -> Signal | None:
    """The rep's last email counts. Anything after it, or no conversation before it, is not a follow-up to chase."""
    sent = [activity for activity in activities if activity.kind == "email_out" and activity.by_rep]
    if not sent or future_commitment:
        return None
    last = max(sent, key=lambda activity: activity.at)
    if any(activity.at > last.at for activity in activities):
        return None
    if not any(activity.kind in _CONVERSATION and activity.at < last.at for activity in activities):
        return None
    sent_on = _local_date(last.at, tz_name)
    days = (_local_date(now, tz_name) - sent_on).days
    if days < NO_REPLY_AFTER_DAYS or days > NO_REPLY_LOOKBACK_DAYS:
        return None
    payload = {
        "email_at": last.at.astimezone(timezone.utc).isoformat(),
        "email_date": sent_on.isoformat(),
        "subject": last.subject or None,
        "email_id": last.id,
    }
    if contact_name:
        payload["contact_name"] = contact_name
    return Signal(
        "no_reply",
        contact_id=contact_id,
        deal_id=None,
        source_memo_id="",
        due_at=None,
        payload=payload,
        dedupe_key=f"no_reply:{contact_id}:{sent_on.isoformat()}",
        connection_id=connection_id,
    )


def _ts(value) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.isdigit():
        return datetime.fromtimestamp(int(text) / 1000, tz=timezone.utc)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _chunks(items: list[str], size: int = _BATCH) -> Iterator[list[str]]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _window_ms(now: datetime, tz_name: str | None) -> tuple[int, int]:
    tz = ZoneInfo(tz_name or DEFAULT_TZ)
    first = now.astimezone(tz).date() - timedelta(days=NO_REPLY_LOOKBACK_DAYS)
    start = datetime.combine(first, time.min, tzinfo=tz)
    return int(start.timestamp() * 1000), int(now.timestamp() * 1000)


def outbound_request(owner_ids: list[str], start_ms: int, end_ms: int, after: str | None) -> dict:
    body: dict = {
        "limit": _BATCH,
        "properties": _PROPERTIES["emails"],
        "sorts": [{"propertyName": "hs_timestamp", "direction": "DESCENDING"}],
        "filterGroups": [{"filters": [
            {"propertyName": "hs_email_direction", "operator": "EQ", "value": "EMAIL"},
            {"propertyName": "hubspot_owner_id", "operator": "IN", "values": list(owner_ids)},
            {"propertyName": "hs_timestamp", "operator": "BETWEEN", "value": str(start_ms), "highValue": str(end_ms)},
        ]}],
    }
    if after:
        body["after"] = after
    return {"method": "POST", "path": "/crm/v3/objects/emails/search", "json": body}


def _associations_request(from_type: str, to_type: str, ids: list[str]) -> dict:
    return {
        "method": "POST",
        "path": f"/crm/v4/associations/{from_type}/{to_type}/batch/read",
        "json": {"inputs": [{"id": oid} for oid in ids]},
    }


def _batch_read_request(object_type: str, ids: list[str], properties: list[str]) -> dict:
    return {
        "method": "POST",
        "path": f"/crm/v3/objects/{object_type}/batch/read",
        "json": {"properties": properties, "inputs": [{"id": oid} for oid in ids]},
    }


def _email_activity(row: dict, rep_owners: set[str]) -> Activity | None:
    """A bounced or scheduled email did not reach anyone, so it neither starts nor answers anything."""
    props = row.get("properties") or {}
    at = _ts(props.get("hs_timestamp"))
    if at is None:
        return None
    oid = str(row.get("id") or "")
    direction = str(props.get("hs_email_direction") or "").upper()
    if direction == "INCOMING_EMAIL":
        return Activity("email_in", at, oid)
    if direction not in _OUTGOING:
        return None
    if str(props.get("hs_email_status") or "").upper() not in _SENT_STATUSES:
        return None
    subject = " ".join(str(props.get("hs_email_subject") or "").split()) or None
    by_rep = direction == "EMAIL" and str(props.get("hubspot_owner_id") or "") in rep_owners
    return Activity("email_out", at, oid, subject=subject, by_rep=by_rep)


def _engagement_activity(kind: str, row: dict) -> Activity | None:
    at = _ts((row.get("properties") or {}).get("hs_timestamp"))
    if at is None:
        return None
    return Activity(_ENGAGEMENT_KIND[kind], at, str(row.get("id") or ""))


def _envelope(items: list[dict], coverage: str, *, connection_id: str, observed_at: str, reason: str | None = None) -> dict:
    envelope = read_envelope(
        items=items,
        coverage=coverage,
        observed_at=observed_at,
        connection_id=connection_id,
        object_type="email",
        reason=reason,
    )
    envelope["connection_id"] = connection_id
    return envelope


def collect_no_reply(
    provider: str,
    fetch: Callable[[dict], dict],
    *,
    connection_id: str,
    observed_at: str,
    rep_email: str | None,
    now: datetime,
    tz_name: str | None,
    max_pages: int = _MAX_PAGES,
    max_candidates: int = _MAX_CANDIDATES,
    max_objects: int = _MAX_OBJECTS,
) -> dict:
    """Read, in batches, what happened with each contact the rep emailed 10–30 local days ago.

    Items carry every activity found; the rule decides. A failed call returns no items, so stored cards stay.
    """
    name = str(provider or "").strip().lower()
    if name == "pipedrive":
        return _envelope([], "unavailable", connection_id=connection_id, observed_at=observed_at, reason="not_available_for_pipedrive")
    if name != "hubspot":
        return _envelope([], "unavailable", connection_id=connection_id, observed_at=observed_at, reason="provider_unavailable")
    wanted = str(rep_email or "").strip().lower()

    def call(request: dict) -> dict:
        return _call(fetch, request, connection_id=connection_id, observed_at=observed_at)

    try:
        owners = _owner_emails("hubspot", fetch, connection_id=connection_id, observed_at=observed_at, max_pages=max_pages)
        rep_owners = {oid for oid, email in owners.items() if wanted and email == wanted}
        if not rep_owners:
            return _envelope([], "unavailable", connection_id=connection_id, observed_at=observed_at, reason="owner_not_found")

        partial = False
        sent: dict[str, Activity] = {}
        start_ms, end_ms = _window_ms(now, tz_name)
        cursor = None
        for _ in range(max_pages):
            payload = call(outbound_request(sorted(rep_owners), start_ms, end_ms, cursor))
            for row in payload.get("results") or []:
                activity = _email_activity(row, rep_owners)
                if activity is not None and activity.kind == "email_out" and activity.by_rep:
                    sent[activity.id] = activity
            cursor = ((payload.get("paging") or {}).get("next") or {}).get("after")
            if not cursor:
                break
        partial = partial or bool(cursor)

        emailed: dict[str, list[Activity]] = {}
        for chunk in _chunks(sorted(sent)):
            for row in call(_associations_request("emails", "contacts", chunk)).get("results") or []:
                email = sent.get(str((row.get("from") or {}).get("id") or ""))
                if email is None:
                    continue
                for target in row.get("to") or []:
                    if target.get("toObjectId") is not None:
                        emailed.setdefault(str(target["toObjectId"]), []).append(email)

        today = _local_date(now, tz_name)
        age = {
            contact: (today - _local_date(max(item.at for item in emails), tz_name)).days
            for contact, emails in emailed.items()
        }
        candidates = sorted(
            (contact for contact, days in age.items() if NO_REPLY_AFTER_DAYS <= days <= NO_REPLY_LOOKBACK_DAYS),
            key=lambda contact: (-age[contact], contact),
        )
        if len(candidates) > max_candidates:
            candidates, partial = candidates[:max_candidates], True

        names: dict[str, Optional[str]] = {}
        for chunk in _chunks(candidates):
            request = _batch_read_request("contacts", chunk, ["firstname", "lastname", "hubspot_owner_id"])
            for row in call(request).get("results") or []:
                props = row.get("properties") or {}
                owner = str(props.get("hubspot_owner_id") or "")
                if owner and owner not in rep_owners:
                    continue
                full = " ".join(
                    part for part in (str(props.get("firstname") or "").strip(), str(props.get("lastname") or "").strip()) if part
                )
                names[str(row.get("id"))] = full or None
        kept = [contact for contact in candidates if contact in names]

        linked: dict[str, dict[str, list[str]]] = {contact: {} for contact in kept}
        unfinished: set[str] = set()
        for kind in _ENGAGEMENTS:
            for chunk in _chunks(kept):
                for row in call(_associations_request("contacts", kind, chunk)).get("results") or []:
                    contact = str((row.get("from") or {}).get("id") or "")
                    if contact not in linked:
                        continue
                    linked[contact][kind] = [
                        str(target["toObjectId"]) for target in row.get("to") or [] if target.get("toObjectId") is not None
                    ]
                    if ((row.get("paging") or {}).get("next") or {}).get("after"):
                        unfinished.add(contact)

        scheduled: dict[str, set[str]] = {kind: set() for kind in _ENGAGEMENTS}
        budget = max_objects
        readable: list[str] = []
        for contact in kept:
            if contact in unfinished:
                partial = True
                continue
            new = {
                kind: [
                    oid for oid in linked[contact].get(kind, [])
                    if oid not in scheduled[kind] and not (kind == "emails" and oid in sent)
                ]
                for kind in _ENGAGEMENTS
            }
            need = sum(len(ids) for ids in new.values())
            if need > budget:
                partial = True
                continue
            budget -= need
            for kind, ids in new.items():
                scheduled[kind].update(ids)
            readable.append(contact)

        found: dict[tuple[str, str], Activity] = {}
        for kind in _ENGAGEMENTS:
            for chunk in _chunks(sorted(scheduled[kind])):
                for row in call(_batch_read_request(kind, chunk, _PROPERTIES[kind])).get("results") or []:
                    activity = _email_activity(row, rep_owners) if kind == "emails" else _engagement_activity(kind, row)
                    if activity is not None:
                        found[(kind, str(row.get("id") or ""))] = activity
    except _ReadFailed as failed:
        return {**failed.envelope, "object_type": "email"}

    items = []
    for contact in readable:
        activities = list(emailed[contact])
        for kind in _ENGAGEMENTS:
            for oid in linked[contact].get(kind, []):
                activity = found.get((kind, oid))
                if activity is not None:
                    activities.append(activity)
        items.append({"contact_id": contact, "contact_name": names.get(contact), "activities": activities})
    return _envelope(items, "partial" if partial else "complete", connection_id=connection_id, observed_at=observed_at)


def _memo_at(memo: dict) -> datetime | None:
    return _ts(memo.get("capture_started_at") or memo.get("created_at"))


def memo_context(memos: list[dict], *, end_of_day: datetime) -> dict[str, tuple[list[Activity], bool]]:
    """Every Vocify memo is a conversation. A commitment of the latest memo due after today suppresses the card."""
    grouped: dict[str, list[tuple[datetime, dict]]] = {}
    for memo in memos:
        contact = str(memo.get("hubspot_contact_id") or "")
        at = _memo_at(memo)
        if contact and at is not None:
            grouped.setdefault(contact, []).append((at, memo))
    context: dict[str, tuple[list[Activity], bool]] = {}
    for contact, rows in grouped.items():
        rows.sort(key=lambda row: row[0])
        activities = [Activity("memo", at, str(memo.get("id") or "")) for at, memo in rows]
        latest = rows[-1][1]
        future = False
        for commitment in _commitments(_intelligence(latest)):
            due = _ts(commitment.get("due_at"))
            if due is not None and due > end_of_day:
                future = True
        context[contact] = (activities, future)
    return context


def _load_memos(supabase, company_id: str, contact_ids: list[str]) -> list[dict]:
    ids = sorted({str(contact) for contact in contact_ids if contact})
    memos: list[dict] = []
    for chunk in _chunks(ids, _MEMO_CHUNK):
        result = (
            supabase.table("memos")
            .select("id,hubspot_contact_id,created_at,capture_started_at,extraction")
            .eq("company_id", company_id)
            .in_("hubspot_contact_id", chunk)
            .execute()
        )
        memos.extend(result.data or [])
    return memos


def _observed_at(now: datetime) -> str:
    return now.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def refresh_no_reply(
    supabase,
    *,
    company_id: str,
    user_id: str,
    rep_email: str | None,
    connection: dict,
    fetch: Callable[[dict], dict],
    now: datetime,
    tz_name: str | None,
    max_pages: int = _MAX_PAGES,
    max_objects: int = _MAX_OBJECTS,
) -> dict:
    """Write new no_reply cards. Only a complete read resolves; a failed one touches nothing."""
    connection_id = str(connection.get("id") or "")
    observed_at = _observed_at(now)
    envelope = collect_no_reply(
        str(connection.get("provider") or ""),
        fetch,
        connection_id=connection_id,
        observed_at=observed_at,
        rep_email=rep_email,
        now=now,
        tz_name=tz_name,
        max_pages=max_pages,
        max_objects=max_objects,
    )
    result = {"coverage": envelope["coverage"], "reason": envelope.get("reason"), "inserted": 0, "resolved": 0}
    if result["coverage"] not in {"complete", "partial"}:
        return result
    items = envelope["items"]
    try:
        memos = _load_memos(supabase, company_id, [item["contact_id"] for item in items])
    except Exception:
        logger.warning("no_reply memo read failed", extra={"company_id": company_id}, exc_info=True)
        return {**result, "coverage": "unavailable", "reason": "memos_unavailable"}
    context = memo_context(memos, end_of_day=day_end(now, tz_name or DEFAULT_TZ))
    fresh: list[Signal] = []
    for item in items:
        memo_activities, future = context.get(item["contact_id"], ([], False))
        signal = no_reply_signal(
            item["contact_id"],
            [*item["activities"], *memo_activities],
            now=now,
            tz_name=tz_name,
            connection_id=connection_id,
            future_commitment=future,
            contact_name=item.get("contact_name"),
        )
        if signal is not None:
            fresh.append(signal)

    stored = (
        supabase.table("action_signals")
        .select("*")
        .eq("company_id", company_id)
        .eq("user_id", user_id)
        .eq("connection_id", connection_id)
        .eq("type", "no_reply")
        .execute()
    ).data or []
    plan = plan_reconcile(stored=stored, fresh=fresh, now=now, source_available=True)
    for signal in plan["insert"]:
        supabase.table("action_signals").upsert(
            {
                "company_id": company_id,
                "user_id": user_id,
                "connection_id": connection_id,
                "contact_id": signal.contact_id,
                "deal_id": None,
                "memo_id": None,
                "type": signal.type,
                "dedupe_key": signal.dedupe_key,
                "payload": signal.payload,
                "status": "pending",
                "coverage": "complete",
                "observed_at": observed_at,
            },
            on_conflict="company_id,user_id,connection_id,dedupe_key",
            ignore_duplicates=True,
        ).execute()
        result["inserted"] += 1
    by_key = {row.get("dedupe_key"): row for row in stored}
    for change in plan["reopen"]:
        row = by_key[change["dedupe_key"]]
        (
            supabase.table("action_signals")
            .update({
                "status": "pending",
                "previous_status": "snoozed",
                "version": change["version"],
                "payload": change["payload"],
                "snoozed_until": None,
                "observed_at": observed_at,
            })
            .eq("id", row["id"])
            .eq("status", "snoozed")
            .eq("version", change["expected_version"])
            .execute()
        )
    if result["coverage"] != "complete":
        return result
    for key in plan["resolve"]:
        row = by_key[key]
        version = int(row.get("version") or 1)
        (
            supabase.table("action_signals")
            .update({
                "status": "resolved",
                "previous_status": row.get("status"),
                "version": version + 1,
                "observed_at": observed_at,
            })
            .eq("id", row["id"])
            .eq("version", version)
            .execute()
        )
        result["resolved"] += 1
    return result
