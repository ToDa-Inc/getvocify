"""A contact's latest interactions, exactly as HubSpot and Vocify hold them, and a short summary that may only say what
those interactions say.

Every interaction carries an id (`hubspot:note:123`, `vocify:memo:<uuid>`). The summary's lines must cite those ids;
a line citing nothing, or anything that was not read, is dropped. Sources that could not be read are reported as such
(`not_allowed` when the HubSpot connection lacks the scope, e.g. emails need `sales-email-read`), never as "nothing".

Besides the contact's own activity: what was said with other people at the contact's company (HubSpot activity filed
under the company, and Vocify conversations with its other contacts), each with who it was with, so a rep calling
someone new at a company knows what the company already heard.
"""

from __future__ import annotations

import asyncio

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
# What others at the company said: conversations, not their to-dos.
_COMPANY_KINDS = ("emails", "notes", "calls", "meetings")
_PERSON_PROPERTIES = ["firstname", "lastname", "jobtitle"]
# HubSpot's contact-to-company "Primary" association.
_PRIMARY_COMPANY_TYPE = 1
# A big company has thousands of contacts: Vocify conversations are looked up for this many of them at most.
COLLEAGUES_LIMIT = 500
COMPANY_SUMMARY_LINES = 2


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


async def _read_kind(client: Any, obj: str, oid: str, kind: str) -> tuple[list[dict], str]:
    """One kind of HubSpot activity associated with a record: the rows (newest 50), and whether it could be read."""
    kind_type, properties, _ = _HUBSPOT_KINDS[kind]
    try:
        ids = _associated_ids(await client.get(f"/crm/v4/objects/{obj}/{oid}/associations/{kind}"))
        if not ids:
            return [], "read"
        # The newest are the ones that matter; HubSpot lists associations oldest first.
        read = await client.post(
            f"/crm/v3/objects/{kind}/batch/read",
            data={"inputs": [{"id": i} for i in ids[-50:]], "properties": properties},
        )
        return (read or {}).get("results", []) or [], "read"
    except Exception as error:  # one kind failing never hides the others
        return [], _status_of(error)


def _interaction(kind: str, row: dict) -> Optional[dict]:
    kind_type, _, text_of = _HUBSPOT_KINDS[kind]
    props = row.get("properties") or {}
    text = text_of(props)
    occurred = _iso(props.get("hs_timestamp"))
    if not text or not occurred:
        return None
    return {"id": f"hubspot:{kind_type}:{row.get('id')}", "type": kind_type, "occurred_at": occurred, "text": text, "source": "hubspot"}


async def read_hubspot_activity(client: Any, contact_id: str) -> tuple[list[dict], dict[str, str]]:
    """The contact's HubSpot emails, notes, calls, meetings and tasks; and, per kind, whether it could be read."""
    kinds = list(_HUBSPOT_KINDS)
    results = await asyncio.gather(*(_read_kind(client, "contacts", contact_id, kind) for kind in kinds))
    interactions: list[dict] = []
    sources: dict[str, str] = {}
    for kind, (rows, status) in zip(kinds, results):
        sources[kind] = status
        interactions += [item for item in (_interaction(kind, row) for row in rows) if item]
    return interactions, sources


async def read_hubspot_company(client: Any, contact_id: str) -> tuple[Optional[dict], str]:
    """The contact's company in HubSpot: its primary one, or its only one. Several and none primary is not guessed
    ("ambiguous"). Only its name: the rep sees the rest in the CRM."""
    try:
        rows = ((await client.get(f"/crm/v4/objects/contacts/{contact_id}/associations/companies")) or {}).get("results", []) or []
        primary = [
            row for row in rows
            if any(t.get("typeId") == _PRIMARY_COMPANY_TYPE and t.get("category") == "HUBSPOT_DEFINED" for t in row.get("associationTypes") or [])
        ]
        ids = _associated_ids({"results": primary or rows})
        if not ids:
            return None, "read"
        if len(ids) > 1:
            return None, "ambiguous"
        row = await client.get(f"/crm/v3/objects/companies/{ids[0]}", params={"properties": "name"})
    except Exception as error:
        return None, _status_of(error)
    name = _clean(((row or {}).get("properties") or {}).get("name")) or None
    return {"id": f"hubspot:company:{ids[0]}", "name": name}, "read"


def _person(props: dict) -> Optional[dict]:
    name = " ".join(p for p in (_clean(props.get("firstname")), _clean(props.get("lastname"))) if p)
    return {"name": name, "title": _clean(props.get("jobtitle")) or None} if name else None


async def read_people(client: Any, contact_ids: list[str]) -> dict[str, dict]:
    """Name and job title of HubSpot contacts, by id (those without a name are left out)."""
    people: dict[str, dict] = {}
    for start in range(0, len(contact_ids), 100):
        try:
            read = await client.post(
                "/crm/v3/objects/contacts/batch/read",
                data={"inputs": [{"id": c} for c in contact_ids[start:start + 100]], "properties": _PERSON_PROPERTIES},
            )
        except Exception:
            logger.warning("Recent activity: names of %d contacts could not be read", len(contact_ids[start:start + 100]), exc_info=True)
            continue
        for row in (read or {}).get("results", []) or []:
            person = _person(row.get("properties") or {})
            if person:
                people[str(row.get("id"))] = person
    return people


async def _engagement_contacts(client: Any, kind: str, ids: list[str]) -> dict[str, list[str]]:
    """Which contacts each engagement is associated with."""
    if not ids:
        return {}
    read = await client.post(f"/crm/v4/associations/{kind}/contacts/batch/read", data={"inputs": [{"id": i} for i in ids]})
    out: dict[str, list[str]] = {}
    for result in (read or {}).get("results", []) or []:
        out[str((result.get("from") or {}).get("id"))] = [str(link["toObjectId"]) for link in result.get("to") or [] if link.get("toObjectId")]
    return out


async def read_company_activity(client: Any, company: dict, contact_id: str, already: set[str]) -> tuple[list[dict], list[str], dict[str, str]]:
    """What others at the company said in HubSpot: the company's emails, notes, calls and meetings, without what is
    the contact's own (already read, or associated with the contact), each with the colleague it was with (`with_id`,
    None when filed on the company alone). Also the company's other contacts (at most COLLEAGUES_LIMIT), and per
    kind whether it could be read."""
    company_id = company["id"].split(":")[-1]

    async def kind_part(kind: str):
        rows, status = await _read_kind(client, "companies", company_id, kind)
        items = [item for item in (_interaction(kind, row) for row in rows) if item and item["id"] not in already]
        try:
            links = await _engagement_contacts(client, kind, [item["id"].split(":")[-1] for item in items])
        except Exception as error:
            return [], _status_of(error)
        kept = []
        for item in items:
            contacts = links.get(item["id"].split(":")[-1], [])
            if contact_id in contacts:
                continue
            others = [c for c in contacts if c != contact_id]
            kept.append({**item, "with_id": others[0] if others else None})
        return kept, status

    async def colleagues() -> tuple[list[str], str]:
        try:
            ids = _associated_ids(await client.get(f"/crm/v4/objects/companies/{company_id}/associations/contacts", params={"limit": 500}))
        except Exception as error:
            return [], _status_of(error)
        return [c for c in ids if c != contact_id][:COLLEAGUES_LIMIT], "read"

    parts = await asyncio.gather(*(kind_part(kind) for kind in _COMPANY_KINDS), colleagues())
    interactions: list[dict] = []
    sources: dict[str, str] = {}
    for kind, (items, status) in zip(_COMPANY_KINDS, parts[:-1]):
        interactions += items
        sources[kind] = status
    others, sources["contacts"] = parts[-1]
    return interactions, others, sources


def with_people(interactions: list[dict], people: dict[str, dict]) -> list[dict]:
    """`with_id` replaced by the person it names (None when unknown or filed on the company alone)."""
    out = []
    for item in interactions:
        rest = {k: v for k, v in item.items() if k != "with_id"}
        out.append({**rest, "with": people.get(item.get("with_id") or "")})
    return out


def memo_interactions(memos: list[dict], *, colleagues: bool = False) -> list[dict]:
    """Vocify's own recorded conversations: the first sentence of each one's summary. With `colleagues`, each also
    names the contact it was with (`with_id`, see `with_people`)."""
    out = []
    for memo in memos:
        summary = ((memo.get("extraction") or {}).get("summary")) or ""
        text = _join(plain_sentence(summary))
        occurred = memo.get("capture_started_at") or memo.get("created_at")
        if not text or not occurred:
            continue
        stamp = datetime.fromisoformat(str(occurred).replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        item = {"id": f"vocify:memo:{memo.get('id')}", "type": "vocify_conversation", "occurred_at": stamp, "text": text, "source": "vocify"}
        if colleagues:
            item["with_id"] = str(memo.get("hubspot_contact_id") or "") or None
        out.append(item)
    return out


def without_pushed(interactions: list[dict], pushed: set[str]) -> list[dict]:
    """The HubSpot calls and notes Vocify itself logged for a conversation it recorded are that conversation: kept
    once, as Vocify's."""
    return [item for item in interactions if item["id"] not in pushed]


def newest_first(interactions: list[dict]) -> list[dict]:
    return sorted(interactions, key=lambda item: item["occurred_at"], reverse=True)[:INTERACTION_LIMIT]


def _item_line(item: dict) -> str:
    who = item.get("with")
    person = ""
    if who:
        person = f" with {who['name']} ({who['title']})" if who.get("title") else f" with {who['name']}"
    return f"[{item['id']}] {item['occurred_at'][:10]} {item['type']}{person}: {item['text']}"


def summary_prompt(interactions: list[dict], company: Optional[dict], company_interactions: list[dict] = ()) -> list[dict]:
    items = "THIS CONTACT:\n" + ("\n".join(_item_line(i) for i in interactions) or "(nothing)")
    if company_interactions:
        items += f"\n\nOTHER PEOPLE AT {company.get('name') or 'THE COMPANY'}:\n" + "\n".join(_item_line(i) for i in company_interactions)
    return [
        {
            "role": "system",
            "content": (
                "You brief a sales rep in a few seconds, right before they call this contact. Use ONLY the items "
                "given; never add facts, numbers, names or dates that are not in them. Write short notes of at most "
                "12 words each, not full sentences, most useful first: what is pending or promised, then where things "
                "stand, then anything to bring up. Each line is about one item where possible. Never write people's "
                "names or dates: the rep sees who and when next to each line. Every line cites the ids of the items "
                "it comes from.\n"
                f'"lines": at most {SUMMARY_LINES} lines about THIS CONTACT, citing only its items.\n'
                f'"company_lines": at most {COMPANY_SUMMARY_LINES} lines on what OTHER PEOPLE AT the company already '
                "discussed (so the rep does not pitch from scratch), citing only their items.\n"
                "Answer in the language the items are mostly written in. Reply as JSON: "
                '{"lines": [{"text": "...", "sources": ["<item id>", ...]}], "company_lines": [...]}. '
                "Leave a list empty when its items say nothing useful."
            ),
        },
        {"role": "user", "content": items},
    ]


def grounded_lines(answer: Any, interactions: list[dict], limit: int = SUMMARY_LINES, key: str = "lines") -> list[dict]:
    """The model's lines (under `key`) that cite only these interactions (and at least one), each with the kind,
    date and, for others at the company, the person of the newest one it cites."""
    read = {i["id"]: i for i in interactions}
    known = set(read)
    lines = []
    for line in (answer or {}).get(key, []) or [] if isinstance(answer, dict) else []:
        text = " ".join(str((line or {}).get("text") or "").split()) if isinstance(line, dict) else ""
        cited = [_resolve(source, known) for source in _citations(line)]
        if text and cited and all(source in known for source in cited):
            newest = max((read[c] for c in cited), key=lambda item: item["occurred_at"])
            out = {"text": text, "sources": cited, "type": newest["type"], "occurred_at": newest["occurred_at"]}
            if "with" in newest:
                out["with"] = newest["with"]
            lines.append(out)
        elif text:
            logger.info("Recent activity summary: dropped a line citing %s", [c for c in cited if c not in known][:5] or "nothing")
    return lines[:limit]


_CITED_ID = re.compile(r"(?:hubspot|vocify):[a-z_]+:[A-Za-z0-9-]+")


def _resolve(source: str, known: set[str]) -> str:
    """A bare id ("d54011d2-…", "525805075670") is the item whose id it ends, when exactly one does."""
    if source in known:
        return source
    matches = [item for item in known if item.endswith(f":{source}")]
    return matches[0] if len(matches) == 1 else source


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
    company_interactions: list[dict] = (),
) -> Optional[dict]:
    """The grounded summary, or None when there is nothing to summarize or the model could not answer."""
    if not interactions and not company_interactions:
        return None
    try:
        answer = await ask(summary_prompt(interactions, company, list(company_interactions)))
    except Exception:
        logger.warning("Recent activity summary: the model did not answer", exc_info=True)
        return None
    lines = grounded_lines(answer, interactions)
    company_lines = grounded_lines(answer, list(company_interactions), COMPANY_SUMMARY_LINES, "company_lines")
    offered = answer.get("lines") if isinstance(answer, dict) else None
    logger.info(
        "Recent activity summary: kept %d of %d lines (%d items), %d company lines (%d items)",
        len(lines), len(offered) if isinstance(offered, list) else -1, len(interactions), len(company_lines), len(company_interactions),
    )
    return {"lines": lines, "company_lines": company_lines}
