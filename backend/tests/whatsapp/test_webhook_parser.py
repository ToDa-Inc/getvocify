from app.services.whatsapp.webhook_parser import parse_webhook


def _interactive(kind, inner):
    return {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {"messages": [{
            "id": "wamid.1",
            "from": "34600111222",
            "timestamp": "1",
            "type": "interactive",
            "interactive": {"type": kind, kind: inner},
        }]}}]}],
    }


def test_parses_button_reply():
    msgs = parse_webhook(_interactive("button_reply", {"id": "act:approve", "title": "Actualizar"}))
    assert len(msgs) == 1
    assert msgs[0].type == "button"
    assert msgs[0].button_id == "act:approve"


def test_parses_list_reply():
    msgs = parse_webhook(_interactive("list_reply", {"id": "pick:skip_deal", "title": "Sin deal"}))
    assert msgs[0].button_id == "pick:skip_deal"
    assert msgs[0].type == "button"
