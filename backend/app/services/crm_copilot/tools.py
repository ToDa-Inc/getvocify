from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from app.models.approval import ContactMatch
from app.models.memo import ApproveMemoRequest, MemoExtraction
from app.services.crm_copilot.prompts import SKILL_BODIES
from app.services.hubspot.account_info import (
    build_company_record_url,
    build_contact_record_url,
    build_deal_record_url,
)
from app.services.whatsapp.copy import briefing_text

WRITE_TOOLS = {
    "apply_write",
    "create_note",
    "create_task",
    "create_contact",
    "create_deal",
}


def confirmation_required(name: str) -> bool:
    return name in WRITE_TOOLS


def _fn(name: str, description: str, properties: dict, required: Optional[list] = None) -> dict:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return {"type": "function", "function": {"name": name, "description": description, "parameters": schema}}


OPENAI_TOOLS = [
    _fn("load_skill", "Load a skill body.", {"name": {"type": "string"}}, ["name"]),
    _fn("remember", "Store a durable seller fact.", {"text": {"type": "string"}}, ["text"]),
    _fn("search_contacts", "Search HubSpot contacts.", {"query": {"type": "string"}}, ["query"]),
    _fn("get_contact", "Get a contact by id, including HubSpot URL.", {"contact_id": {"type": "string"}}, ["contact_id"]),
    _fn("search_companies", "Search companies by name.", {"query": {"type": "string"}}, ["query"]),
    _fn("get_company", "Get a company by id.", {"company_id": {"type": "string"}}, ["company_id"]),
    _fn("search_deals", "Search deals by name.", {"query": {"type": "string"}}, ["query"]),
    _fn("get_deal", "Get a deal by id, including HubSpot URL.", {"deal_id": {"type": "string"}}, ["deal_id"]),
    _fn(
        "list_associated_deals",
        "List deals associated to a contact.",
        {"contact_id": {"type": "string"}},
        ["contact_id"],
    ),
    _fn(
        "list_tasks",
        "List tasks for a contact or deal.",
        {"contact_id": {"type": "string"}, "deal_id": {"type": "string"}},
    ),
    _fn(
        "extract_sales_update",
        "Extract CRM fields from a sales dump or voice transcript. Not for questions.",
        {"transcript": {"type": "string"}},
        ["transcript"],
    ),
    _fn(
        "preview_write",
        "Preview a memo/extraction write against a contact (skip_deal default true).",
        {
            "contact_id": {"type": "string"},
            "deal_id": {"type": "string"},
            "skip_deal": {"type": "boolean"},
            "memo_id": {"type": "string"},
        },
    ),
    _fn(
        "apply_write",
        "Write to HubSpot. Pauses for user confirm. Use memo_id after extract, or object_type+object_id+properties.",
        {
            "memo_id": {"type": "string"},
            "object_type": {"type": "string", "enum": ["contacts", "companies", "deals"]},
            "object_id": {"type": "string"},
            "properties": {"type": "object"},
            "skip_deal": {"type": "boolean"},
        },
    ),
    _fn(
        "create_note",
        "Create a HubSpot note. Pauses for confirm.",
        {
            "body": {"type": "string"},
            "contact_id": {"type": "string"},
            "deal_id": {"type": "string"},
            "company_id": {"type": "string"},
        },
        ["body"],
    ),
    _fn(
        "create_task",
        "Create a HubSpot task. Pauses for confirm.",
        {
            "subject": {"type": "string"},
            "due_date": {"type": "string", "description": "ISO datetime"},
            "contact_id": {"type": "string"},
            "deal_id": {"type": "string"},
            "body": {"type": "string"},
        },
        ["subject"],
    ),
    _fn(
        "create_contact",
        "Create a HubSpot contact. Pauses for confirm.",
        {
            "firstname": {"type": "string"},
            "lastname": {"type": "string"},
            "email": {"type": "string"},
            "phone": {"type": "string"},
            "jobtitle": {"type": "string"},
        },
    ),
    _fn(
        "create_deal",
        "Create a HubSpot deal. Pauses for confirm.",
        {
            "dealname": {"type": "string"},
            "contact_id": {"type": "string"},
            "company_id": {"type": "string"},
            "amount": {"type": "string"},
        },
        ["dealname"],
    ),
    _fn(
        "offer_user_choices",
        "Pause and show a WhatsApp list. Use when several contacts/deals match.",
        {
            "prompt": {"type": "string"},
            "choices": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"id": {"type": "string"}, "label": {"type": "string"}},
                    "required": ["id", "label"],
                },
            },
        },
        ["prompt", "choices"],
    ),
]


@dataclass
class CopilotContext:
    supabase: Any
    user_id: str
    artifacts: dict
    message_id: str = ""
    conversation_id: Optional[str] = None
    audio_url: Optional[str] = None
    extract_memo: Any = None
    hs: Any = None


@dataclass
class HubSpotBundle:
    client: Any
    connection: dict
    search: Any
    contacts: Any
    companies: Any
    deals: Any
    associations: Any
    tasks: Any
    preview: Any
    provider: Any

    @classmethod
    def from_provider(cls, provider: Any) -> "HubSpotBundle":
        from app.services.hubspot import (
            HubSpotAssociationService,
            HubSpotCompanyService,
            HubSpotContactService,
            HubSpotDealService,
            HubSpotPreviewService,
            HubSpotSearchService,
            HubSpotTasksService,
        )

        search = HubSpotSearchService(provider._client)
        schema = provider._schema_service()
        deals = HubSpotDealService(provider._client, search, schema)
        contacts = HubSpotContactService(provider._client, search)
        companies = HubSpotCompanyService(provider._client, search)
        assoc = HubSpotAssociationService(provider._client)
        return cls(
            client=provider._client,
            connection=provider._connection,
            search=search,
            contacts=contacts,
            companies=companies,
            deals=deals,
            associations=assoc,
            tasks=HubSpotTasksService(provider._client),
            preview=HubSpotPreviewService(
                provider._client,
                deals,
                schema,
                associations=assoc,
                contact_service=contacts,
                company_service=companies,
            ),
            provider=provider,
        )

    def hosting(self) -> tuple[str, Optional[str], str]:
        md = self.connection.get("metadata") or {}
        return str(md.get("portal_id") or ""), md.get("ui_domain"), md.get("region") or "na1"


def _copilot_dict(ctx: Optional[CopilotContext]) -> dict:
    if ctx is None:
        return {}
    return ctx.artifacts.setdefault("copilot", {})


def _bundle(ctx: CopilotContext) -> HubSpotBundle:
    if ctx.hs is not None:
        return ctx.hs
    from app.services.crm_providers import build_crm_provider, resolve_sync_connection

    conn = resolve_sync_connection(ctx.supabase, ctx.user_id)
    if not conn:
        raise ValueError("No CRM connected")
    if (conn.get("provider") or "").lower() != "hubspot":
        raise ValueError("WhatsApp CRM copilot currently supports HubSpot only")
    ctx.hs = HubSpotBundle.from_provider(build_crm_provider(ctx.supabase, conn))
    return ctx.hs


def _props(obj: Any) -> dict:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj.get("properties") or {}
    return getattr(obj, "properties", None) or {}


def _oid(obj: Any) -> str:
    if isinstance(obj, dict):
        return str(obj.get("id") or "")
    return str(getattr(obj, "id", "") or "")


def _contact_brief(obj: Any, hs: HubSpotBundle) -> dict:
    props = _props(obj)
    cid = _oid(obj)
    name = f"{props.get('firstname') or ''} {props.get('lastname') or ''}".strip() or props.get("email") or cid
    portal, ui_domain, region = hs.hosting()
    url = build_contact_record_url(portal, cid, ui_domain=ui_domain, region=region) if portal and cid else None
    return {
        "object": "contact",
        "id": cid,
        "name": name,
        "email": props.get("email"),
        "phone": props.get("phone") or props.get("mobilephone"),
        "jobtitle": props.get("jobtitle"),
        "url": url,
        "contact_id": cid,
        "contact_url": url,
    }


def _company_brief(obj: Any, hs: HubSpotBundle) -> dict:
    props = _props(obj)
    cid = _oid(obj)
    portal, ui_domain, region = hs.hosting()
    url = build_company_record_url(portal, cid, ui_domain=ui_domain, region=region) if portal and cid else None
    return {
        "object": "company",
        "id": cid,
        "name": props.get("name"),
        "domain": props.get("domain"),
        "url": url,
        "company_id": cid,
    }


def _deal_brief(obj: Any, hs: HubSpotBundle) -> dict:
    props = _props(obj)
    did = _oid(obj)
    portal, ui_domain, region = hs.hosting()
    url = build_deal_record_url(portal, did, ui_domain=ui_domain, region=region) if portal and did else None
    return {
        "object": "deal",
        "id": did,
        "name": props.get("dealname"),
        "amount": props.get("amount"),
        "stage": props.get("dealstage"),
        "url": url,
        "deal_id": did,
        "deal_url": url,
    }


async def execute_tool(name: str, args: dict, ctx: Any) -> dict:
    args = args or {}
    try:
        return await _execute(name, args, ctx)
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def _execute(name: str, args: dict, ctx: Any) -> dict:
    if name == "load_skill":
        skill = str(args.get("name") or "")
        body = SKILL_BODIES.get(skill)
        if not body:
            return {"ok": False, "error": f"unknown skill {skill}"}
        return {"name": skill, "content": body}
    if name == "remember":
        text = str(args.get("text") or "").strip()
        if not text:
            return {"ok": False, "error": "empty memory"}
        copilot = _copilot_dict(ctx)
        memory = copilot.setdefault("memory", [])
        memory.append(text[:500])
        copilot["memory"] = memory[-40:]
        return {"ok": True}
    if name == "offer_user_choices":
        return {"ok": True, "paused": True}

    if ctx is None:
        return {"ok": False, "error": "missing copilot context"}
    hs = _bundle(ctx)

    if name == "search_contacts":
        hits = await hs.search.search_contacts_by_query(str(args.get("query") or ""), limit=8)
        return {"contacts": [_contact_brief(c, hs) for c in hits]}
    if name == "get_contact":
        obj = await hs.contacts.get(str(args["contact_id"]))
        return _contact_brief(obj, hs)
    if name == "search_companies":
        hits = await hs.search.find_companies_by_name(str(args.get("query") or ""), limit=8)
        return {"companies": [_company_brief(c, hs) for c in hits]}
    if name == "get_company":
        obj = await hs.companies.get(str(args["company_id"]))
        return _company_brief(obj, hs)
    if name == "search_deals":
        rows = await hs.search.search_deals_by_query(str(args.get("query") or ""), limit=8)
        return {"deals": [_deal_brief(r, hs) for r in rows]}
    if name == "get_deal":
        obj = await hs.deals.get(str(args["deal_id"]))
        return _deal_brief(obj, hs)
    if name == "list_associated_deals":
        ids = await hs.associations.get_associations("contacts", str(args["contact_id"]), "deals")
        deals = []
        for deal_id in ids[:8]:
            try:
                deals.append(_deal_brief(await hs.deals.get(deal_id), hs))
            except Exception:
                deals.append({"id": deal_id, "deal_id": deal_id})
        return {"deals": deals}
    if name == "list_tasks":
        if args.get("deal_id"):
            tasks = await hs.tasks.list_tasks_for_deal(str(args["deal_id"]))
        elif args.get("contact_id"):
            tasks = await hs.tasks.list_tasks_for_contact(str(args["contact_id"]))
        else:
            return {"ok": False, "error": "contact_id or deal_id required"}
        return {"tasks": tasks}
    if name == "extract_sales_update":
        return await _extract_sales_update(str(args.get("transcript") or ""), ctx)
    if name == "preview_write":
        return await _preview_write(args, ctx, hs)
    if name == "apply_write":
        return await _apply_write(args, ctx, hs)
    if name == "create_note":
        return await _create_note(args, hs)
    if name == "create_task":
        return await _create_task(args, hs)
    if name == "create_contact":
        props = {k: v for k, v in args.items() if v and k in {"firstname", "lastname", "email", "phone", "jobtitle"}}
        obj = await hs.contacts.create(props)
        return _contact_brief(obj, hs)
    if name == "create_deal":
        props = {"dealname": args["dealname"]}
        if args.get("amount"):
            props["amount"] = str(args["amount"])
        obj = await hs.deals.create(
            props,
            contact_id=args.get("contact_id"),
            company_id=args.get("company_id"),
        )
        return _deal_brief(obj, hs)
    return {"ok": False, "error": f"unknown tool {name}"}


async def _extract_sales_update(transcript: str, ctx: CopilotContext) -> dict:
    if ctx.extract_memo:
        memo_id, extraction = await ctx.extract_memo(transcript)
        if not extraction:
            return {"ok": False, "error": "extract failed"}
        payload = extraction.model_dump() if hasattr(extraction, "model_dump") else dict(extraction)
        copilot = _copilot_dict(ctx)
        copilot["memo_id"] = memo_id
        copilot["extraction"] = payload
        return {"ok": True, "memo_id": memo_id, "extraction": payload}
    from app.services.extraction import ExtractionService

    extraction = await ExtractionService().extract(transcript)
    payload = extraction.model_dump()
    _copilot_dict(ctx)["extraction"] = payload
    return {"ok": True, "extraction": payload}


async def _preview_write(args: dict, ctx: CopilotContext, hs: HubSpotBundle) -> dict:
    copilot = _copilot_dict(ctx)
    extraction_data = copilot.get("extraction")
    if not extraction_data:
        return {"ok": False, "error": "no extraction; call extract_sales_update first"}
    extraction = MemoExtraction(**extraction_data) if not isinstance(extraction_data, MemoExtraction) else extraction_data
    contact_id = args.get("contact_id") or copilot.get("last_contact_id")
    deal_id = args.get("deal_id") or copilot.get("last_deal_id")
    skip_deal = args.get("skip_deal")
    if skip_deal is None:
        skip_deal = not deal_id
    memo_id = args.get("memo_id") or copilot.get("memo_id") or str(uuid4())
    try:
        memo_uuid = UUID(str(memo_id))
    except Exception:
        memo_uuid = uuid4()
    selected = ContactMatch(contact_id=str(contact_id), name="") if contact_id else None
    preview = await hs.preview.build_preview(
        memo_id=memo_uuid,
        transcript=str(extraction.summary or ""),
        extraction=extraction,
        matched_deals=[],
        selected_deal_id=None if skip_deal else deal_id,
        skip_deal=bool(skip_deal),
        selected_contact=selected,
    )
    # memo_id on ApprovalPreview is UUID
    text = briefing_text(preview)
    copilot["last_preview_text"] = text[:1500]
    copilot["memo_id"] = str(getattr(preview, "memo_id", None) or memo_id)
    return {
        "ok": True,
        "memo_id": copilot["memo_id"],
        "preview_text": text,
        "skip_deal": bool(skip_deal),
        "contact_id": contact_id,
        "deal_id": None if skip_deal else deal_id,
    }


async def _apply_write(args: dict, ctx: CopilotContext, hs: HubSpotBundle) -> dict:
    from app.services.memo_approval import approve_memo_core

    memo_id = args.get("memo_id") or _copilot_dict(ctx).get("memo_id")
    if memo_id:
        payload = ApproveMemoRequest(
            deal_id=args.get("deal_id") or None,
            skip_deal=bool(args.get("skip_deal", True)),
            contact_id=(
                args.get("contact_id")
                or (args.get("object_id") if args.get("object_type") == "contacts" else None)
                or _copilot_dict(ctx).get("last_contact_id")
            ),
        )
        result = await approve_memo_core(ctx.supabase, str(memo_id), ctx.user_id, payload)
        out = {"ok": True, "memo_id": str(memo_id)}
        for key in ("contact_id", "deal_id", "deal_url", "contact_url", "success"):
            if hasattr(result, key):
                out[key] = getattr(result, key)
        return out
    object_type = args.get("object_type")
    object_id = args.get("object_id")
    properties = args.get("properties") or {}
    if not object_type or not object_id or not properties:
        return {"ok": False, "error": "memo_id or object_type+object_id+properties required"}
    if object_type == "contacts":
        obj = await hs.contacts.update(str(object_id), properties)
        return {**_contact_brief(obj, hs), "ok": True}
    if object_type == "companies":
        obj = await hs.companies.update(str(object_id), properties)
        return {**_company_brief(obj, hs), "ok": True}
    if object_type == "deals":
        obj = await hs.deals.update(str(object_id), properties)
        return {**_deal_brief(obj, hs), "ok": True}
    return {"ok": False, "error": f"unsupported object_type {object_type}"}


async def _create_note(args: dict, hs: HubSpotBundle) -> dict:
    from app.services.hubspot.notes import create_note_with_associations

    note_id = await create_note_with_associations(
        hs.client,
        hs.associations,
        note_properties={
            "hs_note_body": str(args.get("body") or ""),
            "hs_timestamp": str(int(datetime.now(timezone.utc).timestamp() * 1000)),
        },
        deal_id=args.get("deal_id"),
        contact_id=args.get("contact_id"),
        company_id=args.get("company_id"),
        memo_id="whatsapp-copilot",
        log_event="copilot_note",
    )
    return {"ok": bool(note_id), "note_id": note_id}


async def _create_task(args: dict, hs: HubSpotBundle) -> dict:
    raw = args.get("due_date")
    if raw:
        due = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    else:
        due = datetime.now(timezone.utc)
    task_id = await hs.tasks.create_task(
        subject=str(args.get("subject") or "Follow-up"),
        due_date=due,
        deal_id=args.get("deal_id"),
        contact_id=args.get("contact_id"),
        body=args.get("body"),
    )
    return {"ok": bool(task_id), "task_id": task_id}
