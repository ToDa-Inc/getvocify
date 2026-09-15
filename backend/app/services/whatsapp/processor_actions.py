"""Action-card send and deal retarget helpers for the WhatsApp processor."""

from __future__ import annotations

from typing import Any, Optional

from app.models.approval import ApprovalPreview
from app.services.whatsapp.actions import (
    ACT_APPROVE,
    ACT_KEEP,
    ACT_RETARGET,
    PICK_NEW_DEAL,
    PICK_SKIP_DEAL,
    PICK_TYPE_NAME,
    PRIMARY_BUTTONS,
    deal_list_sections,
)
from app.services.whatsapp.copy import briefing_text, button_body
from app.services.whatsapp.split import split_text
from app.services.whatsapp.webhook_parser import IncomingMessage

PICK_DEAL_PREFIX = "pick:deal:"
PICK_CONTACT_PREFIX = "pick:contact:"
CONTACT_PROMPT = "¿Quién es el contacto?"
TYPED_SEARCH_PROMPT = "Escribe el nombre del deal"
RETARGET_LIST_BODY = "Elige un deal"
RETARGET_LIST_BUTTON = "Cambiar deal"


def client_kwargs(msg: IncomingMessage) -> dict:
    kwargs: dict = {}
    if getattr(msg, "chat_id", None) and getattr(msg, "account_id", None):
        kwargs["chat_id"] = msg.chat_id
        kwargs["account_id"] = msg.account_id
    return kwargs


def preview_kwargs_for_pick(pick_id: str) -> Optional[dict]:
    pid = (pick_id or "").strip()
    if pid == PICK_SKIP_DEAL:
        return {"skip_deal": True, "selected_deal_id": None, "is_new_deal": False}
    if pid == PICK_NEW_DEAL:
        return {"skip_deal": False, "selected_deal_id": None, "is_new_deal": True}
    if pid.startswith(PICK_DEAL_PREFIX):
        deal_id = pid[len(PICK_DEAL_PREFIX) :]
        if deal_id:
            return {"skip_deal": False, "selected_deal_id": deal_id, "is_new_deal": False}
    if pid.startswith(PICK_CONTACT_PREFIX):
        contact_id = pid[len(PICK_CONTACT_PREFIX) :]
        if contact_id:
            return {
                "skip_deal": True,
                "selected_deal_id": None,
                "is_new_deal": False,
                "contact_id": contact_id,
            }
    return None


def action_from_inbound(text: str) -> Optional[str]:
    t = (text or "").strip()
    if t == ACT_APPROVE:
        return "approve"
    if t == ACT_KEEP:
        return "keep"
    if t == ACT_RETARGET:
        return "retarget"
    if t == PICK_TYPE_NAME:
        return "type_name"
    if t == PICK_SKIP_DEAL:
        return "skip_deal"
    if t == PICK_NEW_DEAL:
        return "new_deal"
    if t.startswith(PICK_DEAL_PREFIX):
        return "pick_deal"
    if t.startswith(PICK_CONTACT_PREFIX):
        return "pick_contact"
    return None


def copy_steps_from_extraction(extraction_data: Optional[dict]) -> tuple[Optional[list], Optional[list]]:
    if not extraction_data:
        return None, None
    steps = extraction_data.get("nextSteps") or []
    raw = extraction_data.get("raw_extraction") or {}
    schedules = raw.get("nextStepSchedules") or extraction_data.get("nextStepSchedules") or []
    return steps, schedules


def deal_options_from_search(results: list[dict]) -> list[dict]:
    options: list[dict] = []
    for deal_data in results or []:
        props = deal_data.get("properties") or {}
        deal_id = str(deal_data.get("id") or deal_data.get("deal_id") or "")
        if not deal_id:
            continue
        options.append(
            {
                "deal_id": deal_id,
                "deal_name": props.get("dealname") or deal_data.get("deal_name") or deal_id,
                "amount": props.get("amount") or deal_data.get("amount"),
                "stage": props.get("dealstage") or deal_data.get("stage"),
                "last_updated": props.get("hs_lastmodifieddate") or deal_data.get("last_updated") or "",
                "match_confidence": 1.0,
                "match_reason": "Manual Search",
            }
        )
    return options


def numbered_retarget_text(sections: list[dict]) -> str:
    lines = [RETARGET_LIST_BODY]
    n = 1
    for section in sections:
        for row in section.get("rows") or []:
            lines.append(f"{n}. {row.get('title') or row.get('id')}")
            n += 1
    return "\n".join(lines)


def pick_id_from_choice(choice: int, artifacts: dict) -> Optional[str]:
    picks = (artifacts or {}).get("retarget_picks") or []
    idx = choice - 1
    if 0 <= idx < len(picks):
        return picks[idx]
    return None


def _contact_list_rows(candidates: list[Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for candidate in candidates[:10]:
        if isinstance(candidate, dict):
            cid = candidate.get("contact_id")
            title = candidate.get("name") or candidate.get("email") or cid
        else:
            cid = getattr(candidate, "contact_id", None)
            title = getattr(candidate, "name", None) or getattr(candidate, "email", None) or cid
        if not cid:
            continue
        rows.append({"id": f"{PICK_CONTACT_PREFIX}{cid}", "title": str(title or cid)[:24]})
    return rows


async def send_action_card(
    *,
    wa_client: Any,
    msg: IncomingMessage,
    preview: ApprovalPreview,
    conv_svc: Any,
    conversation_id: Any,
    memo_id: str,
    artifacts: dict,
    next_steps: Optional[list[str]] = None,
    next_step_schedules: Optional[list[str]] = None,
) -> None:
    kw = client_kwargs(msg)
    candidates = preview.contact_candidates or []
    if candidates and not preview.selected_contact:
        rows = _contact_list_rows(candidates)
        conv_svc.set_state(
            conversation_id,
            "waiting_retarget",
            pending_memo_id=memo_id,
            pending_artifact_ids=artifacts,
        )
        conv_svc.add_message(
            conversation_id, "outbound", CONTACT_PROMPT, "text", {"memo_id": memo_id}
        )
        if rows:
            try:
                await wa_client.send_interactive_list(
                    msg.from_phone,
                    CONTACT_PROMPT,
                    "Contactos",
                    [{"title": "Contacto", "rows": rows}],
                    **kw,
                )
                return
            except Exception:
                pass
        await wa_client.send_text(msg.from_phone, CONTACT_PROMPT, **kw)
        return

    briefing = briefing_text(
        preview, next_steps=next_steps, next_step_schedules=next_step_schedules
    )
    body = button_body(preview, next_steps=next_steps)[:1024]
    conv_svc.set_state(
        conversation_id,
        "waiting_approval",
        pending_memo_id=memo_id,
        pending_artifact_ids=artifacts,
    )
    conv_svc.add_message(
        conversation_id, "outbound", briefing, "extraction_summary", {"memo_id": memo_id}
    )
    for part in split_text(briefing):
        await wa_client.send_text(msg.from_phone, part, **kw)
    await wa_client.send_interactive_buttons(msg.from_phone, body, PRIMARY_BUTTONS, **kw)


async def handle_retarget(
    *,
    wa_client: Any,
    msg: IncomingMessage,
    conv_svc: Any,
    conversation_id: Any,
    memo_id: str,
    artifacts: dict,
    button_id: Optional[str] = None,
    matches: Optional[list] = None,
) -> None:
    del button_id
    options = list(matches) if matches is not None else list((artifacts or {}).get("deal_options") or [])
    sections = deal_list_sections(options, has_deal=bool((artifacts or {}).get("selected_deal_id")))
    pick_ids = [row["id"] for section in sections for row in section.get("rows") or []]
    next_artifacts = {
        **(artifacts or {}),
        "deal_options": options,
        "retarget_picks": pick_ids,
    }
    conv_svc.set_state(
        conversation_id,
        "waiting_retarget",
        pending_memo_id=memo_id,
        pending_artifact_ids=next_artifacts,
    )
    conv_svc.add_message(
        conversation_id, "outbound", RETARGET_LIST_BODY, "text", {"memo_id": memo_id}
    )
    kw = client_kwargs(msg)
    send_list = getattr(wa_client, "send_interactive_list", None)
    if send_list is not None:
        try:
            await send_list(
                msg.from_phone,
                RETARGET_LIST_BODY,
                RETARGET_LIST_BUTTON,
                sections,
                **kw,
            )
            return
        except Exception:
            pass
    await wa_client.send_text(msg.from_phone, numbered_retarget_text(sections), **kw)


async def prompt_typed_search(
    *,
    wa_client: Any,
    msg: IncomingMessage,
    conv_svc: Any,
    conversation_id: Any,
    memo_id: str,
    artifacts: dict,
) -> None:
    conv_svc.set_state(
        conversation_id,
        "waiting_typed_search",
        pending_memo_id=memo_id,
        pending_artifact_ids=artifacts,
    )
    conv_svc.add_message(
        conversation_id, "outbound", TYPED_SEARCH_PROMPT, "text", {"memo_id": memo_id}
    )
    await wa_client.send_text(msg.from_phone, TYPED_SEARCH_PROMPT, **client_kwargs(msg))
