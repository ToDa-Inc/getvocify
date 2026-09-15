"""Semantic action ids for Meta WhatsApp interactive messages."""

ACT_APPROVE = "act:approve"
ACT_KEEP = "act:keep"
ACT_RETARGET = "act:retarget"

PICK_SKIP_DEAL = "pick:skip_deal"
PICK_NEW_DEAL = "pick:new_deal"
PICK_TYPE_NAME = "pick:type_name"

MAX_LIST_ROWS = 10
MAX_DEAL_MATCH_ROWS = 7

PRIMARY_BUTTONS: list[dict[str, str]] = [
    {"id": ACT_APPROVE, "title": "Actualizar"},
    {"id": ACT_KEEP, "title": "No actualizar"},
    {"id": ACT_RETARGET, "title": "Cambiar deal"},
]


def primary_buttons() -> list[dict[str, str]]:
    return PRIMARY_BUTTONS


def _pick_deal_id(deal_id: str) -> str:
    return f"pick:deal:{deal_id}"


def deal_list_sections(matches: list[dict], has_deal: bool = True) -> list[dict]:
    """Build Meta list sections for deal retargeting."""
    del has_deal  # idempotent: Sin deal always included

    rows: list[dict[str, str]] = [{"id": PICK_SKIP_DEAL, "title": "Sin deal"}]

    for match in matches[:MAX_DEAL_MATCH_ROWS]:
        deal_id = str(match.get("deal_id") or "")
        deal_name = str(match.get("deal_name") or deal_id)
        if deal_id:
            rows.append({"id": _pick_deal_id(deal_id), "title": deal_name[:24]})

    rows.append({"id": PICK_NEW_DEAL, "title": "Deal nuevo"})
    rows.append({"id": PICK_TYPE_NAME, "title": "Escribe el nombre"})

    return [{"title": "Deal", "rows": rows[:MAX_LIST_ROWS]}]
