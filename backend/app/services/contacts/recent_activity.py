"""A contact's latest interactions, exactly as HubSpot and Vocify hold them, and a short summary that may only say what
those interactions say.

Every interaction carries an id (`hubspot:note:123`, `vocify:memo:<uuid>`). The summary's lines must cite those ids;
a line citing nothing, or anything that was not read, is dropped. Sources that could not be read are reported as such
(`not_allowed` when the HubSpot connection lacks the scope, e.g. emails need `sales-email-read`), never as "nothing".
"""

from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from app.services.briefs.preparation import plain_sentence

logger = logging.getLogger(__name__)

TEXT_LIMIT = 280
INTERACTION_LIMIT = 12
SUMMARY_LINES = 3

# HubSpot object (as in the v4 association path) -> (interaction type, properties to read, text from properties).
_HUBSPOT_KINDS: dict[str, tuple[str, list[str], Callable[[dict], str]]] = {
    "emails": (
        "email",
        ["hs_timestamp", "hs_email_subject", "hs_email_text", "hs_email_direction"],
        lambda p: _join(p.get("hs_email_subject"), p.get("hs_email_text")),
    ),
    "notes": ("note", ["hs_timestamp", "hs_note_body"], lambda p: _join(p.get("hs_note_body"))),
    "calls": (
        "call",
        ["hs_timestamp", "hs_call_title", "hs_call_body", "hs_call_direction", "hs_call_status"],
        lambda p: _join(p.get("hs_call_title"), p.get("hs_call_body")),
    ),
    "meetings": (
        "meeting",
        ["hs_timestamp", "hs_meeting_title", "hs_meeting_body"],
        lambda p: _join(p.get("hs_meeting_title"), p.get("hs_meeting_body")),
    ),
    "tasks": (
        "task",
        ["hs_timestamp", "hs_task_subject", "hs_task_status"],
        lambda p: _join(p.get("hs_task_subject"), _task_status(p.get("hs_task_status"))),
    ),
}
_COMPANY_PROPERTIES = ["name", "domain", "industry", "numberofemployees"]


_BLOCK_TAG = re.compile(r"</?(p|div|br|li|ul|ol|tr|h[1-6])\b[^>]*>", re.I)


def _clean(value: Any) -> str:
    """Plain text from HubSpot's HTML bodies: blocks become spaces, inline tags (bold, links) just go."""
    text = re.sub(r"<[^>]+>", "", _BLOCK_TAG.sub(" ", str(value or "")))
    return " ".join(html.unescape(text).split())


def _join(*parts: Any) -> str:
    text = " — ".join(p for p in (_clean(part) for part in parts) if p)
    return text if len(text) <= TEXT_LIMIT else text[: TEXT_LIMIT - 1].rstrip() + "…"


def _task_status(status: Any) -> str:
    return {"NOT_STARTED": "open", "IN_PROGRESS": "in progress", "WAITING": "waiting", "COMPLETED": "done"}.get(str(status or ""), "")


def _iso(ms: Any) -> Optional[str]:
    try:
        return datetime.fromtimestamp(int(ms) / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return None


def _status_of(error: Exception) -> str:
    return "not_allowed" if getattr(error, "status_code", None) == 403 else "failed"


def _associated_ids(response: Any) -> list[str]:
    ids: list[str] = []
    for row in (response or {}).get("results", []) or []:
        oid = row.get("toObjectId") or row.get("id")
        if oid is not None and str(oid) not in ids:
            ids.append(str(oid))
    return ids


async def read_hubspot_activity(client: Any, contact_id: str) -> tuple[list[dict], dict[str, str]]:
    """The contact's HubSpot emails, notes, calls, meetings and tasks; and, per kind, whether it could be read."""
    interactions: list[dict] = []
    sources: dict[str, str] = {}
    for kind, (kind_type, properties, text_of) in _HUBSPOT_KINDS.items():
        try:
            ids = _associated_ids(await client.get(f"/crm/v4/objects/contacts/{contact_id}/associations/{kind}"))
            rows: list[dict] = []
            if ids:
                # The newest are the ones that matter; HubSpot lists associations oldest first.
                wanted = ids[-50:]
                read = await client.post(
                    f"/crm/v3/objects/{kind}/batch/read",
                    data={"inputs": [{"id": i} for i in wanted], "properties": properties},
                )
                rows = (read or {}).get("results", []) or []
            sources[kind] = "read"
        except Exception as error:  # one kind failing never hides the others
            sources[kind] = _status_of(error)
            continue
        for row in rows:
            props = row.get("properties") or {}
            text = text_of(props)
            occurred = _iso(props.get("hs_timestamp"))
            if not text or not occurred:
                continue
            interactions.append({"id": f"hubspot:{kind_type}:{row.get('id')}", "type": kind_type, "occurred_at": occurred, "text": text, "source": "hubspot"})
    return interactions, sources


async def read_hubspot_company(client: Any, contact_id: str) -> tuple[Optional[dict], str]:
    """The contact's primary company in HubSpot, or None."""
    try:
        ids = _associated_ids(await client.get(f"/crm/v4/objects/contacts/{contact_id}/associations/companies"))
        if not ids:
            return None, "read"
        row = await client.get(f"/crm/v3/objects/companies/{ids[0]}", params={"properties": ",".join(_COMPANY_PROPERTIES)})
    except Exception as error:
        return None, _status_of(error)
    props = (row or {}).get("properties") or {}
    return {
        "id": f"hubspot:company:{ids[0]}",
        "name": _clean(props.get("name")) or None,
        "domain": _clean(props.get("domain")) or None,
        "industry": _clean(props.get("industry")) or None,
        "employees": _clean(props.get("numberofemployees")) or None,
    }, "read"


def memo_interactions(memos: list[dict]) -> list[dict]:
    """Vocify's own recorded conversations with the contact: the first sentence of each one's summary."""
    out = []
    for memo in memos:
        summary = ((memo.get("extraction") or {}).get("summary")) or ""
        text = _join(plain_sentence(summary))
        occurred = memo.get("capture_started_at") or memo.get("created_at")
        if not text or not occurred:
            continue
        stamp = datetime.fromisoformat(str(occurred).replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        out.append({"id": f"vocify:memo:{memo.get('id')}", "type": "vocify_conversation", "occurred_at": stamp, "text": text, "source": "vocify"})
    return out


def newest_first(interactions: list[dict]) -> list[dict]:
    return sorted(interactions, key=lambda item: item["occurred_at"], reverse=True)[:INTERACTION_LIMIT]


def summary_prompt(interactions: list[dict], company: Optional[dict]) -> list[dict]:
    items = "\n".join(f"[{i['id']}] {i['occurred_at'][:10]} {i['type']}: {i['text']}" for i in interactions)
    if company:
        facts = ", ".join(f"{k}: {v}" for k, v in company.items() if k != "id" and v)
        items += f"\n[{company['id']}] company: {facts}"
    return [
        {
            "role": "system",
            "content": (
                "You brief a sales rep in a few seconds, right before they call this contact. Use ONLY the items "
                "given; never add facts, numbers, names or dates that are not in them. Write at most "
                f"{SUMMARY_LINES} short lines (max 20 words each), most useful first: where things stand, what was "
                "promised or is pending, and anything to bring up. Every line cites the ids of the items it comes "
                'from. Answer in the language the items are mostly written in. Reply as JSON: {"lines": '
                '[{"text": "...", "sources": ["<item id>", ...]}]}. If the items say nothing useful, return {"lines": []}.'
            ),
        },
        {"role": "user", "content": items},
    ]


def grounded_lines(answer: Any, interactions: list[dict], company: Optional[dict]) -> list[dict]:
    """The model's lines that cite only items that were read (and at least one)."""
    known = {i["id"] for i in interactions} | ({company["id"]} if company else set())
    lines = []
    for line in (answer or {}).get("lines", []) if isinstance(answer, dict) else []:
        text = " ".join(str((line or {}).get("text") or "").split())
        cited = _citations(line)
        if text and cited and all(source in known for source in cited):
            lines.append({"text": text, "sources": cited})
        elif text:
            logger.info("Recent activity summary: dropped a line citing %s", [c for c in cited if c not in known][:5] or "nothing")
    return lines[:SUMMARY_LINES]


_CITED_ID = re.compile(r"(?:hubspot|vocify):[a-z_]+:[A-Za-z0-9-]+")


def _citations(line: Any) -> list[str]:
    """The ids a line cites, however the model wrote them: a list or one string, with or without the prompt's brackets."""
    raw = (line or {}).get("sources") if isinstance(line, dict) else None
    if raw is None and isinstance(line, dict):
        raw = line.get("source")
    parts = raw if isinstance(raw, list) else [raw] if raw else []
    cited: list[str] = []
    for part in parts:
        found = _CITED_ID.findall(str(part))
        for item in found or [str(part).strip().strip("[]").strip()]:
            if item and item not in cited:
                cited.append(item)
    return cited


async def summarize(
    interactions: list[dict],
    company: Optional[dict],
    ask: Callable[[list[dict]], Awaitable[Any]],
) -> Optional[dict]:
    """The grounded summary, or None when there is nothing to summarize or the model could not answer."""
    if not interactions:
        return None
    try:
        answer = await ask(summary_prompt(interactions, company))
    except Exception:
        logger.warning("Recent activity summary: the model did not answer", exc_info=True)
        return None
    lines = grounded_lines(answer, interactions, company)
    offered = answer.get("lines") if isinstance(answer, dict) else None
    logger.info(
        "Recent activity summary: kept %d of %d lines (%d items)",
        len(lines), len(offered) if isinstance(offered, list) else -1, len(interactions),
    )
    return {"lines": lines}
