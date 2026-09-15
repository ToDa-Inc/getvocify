from uuid import uuid4

import pytest
from app.models.approval import ApprovalPreview, ContactMatch, ProposedUpdate
from app.services.whatsapp.actions import ACT_APPROVE, ACT_RETARGET, PICK_SKIP_DEAL
from app.services.whatsapp.webhook_parser import IncomingMessage


def _msg() -> IncomingMessage:
    return IncomingMessage(
        message_id="wamid.1",
        from_phone="34600111222",
        timestamp="1",
        type="text",
        text="ok",
    )


def _contact_preview(**overrides) -> ApprovalPreview:
    data = dict(
        memo_id=uuid4(),
        transcript_summary="summary",
        selected_contact=ContactMatch(
            contact_id="c1",
            name="Ana López",
            company_name="Neurtek",
        ),
        selected_deal=None,
        skip_deal=True,
        proposed_updates=[
            ProposedUpdate(
                object_type="contacts",
                field_name="jobtitle",
                field_label="Cargo",
                new_value="Directora",
                current_value="",
                extraction_confidence=0.9,
            ),
        ],
    )
    data.update(overrides)
    return ApprovalPreview(**data)


class FakeWA:
    def __init__(self, sent: list):
        self._sent = sent

    def is_configured(self):
        return True

    async def send_text(self, to, text, **k):
        self._sent.append(("text", text))

    async def send_interactive_buttons(self, to, body, buttons, **k):
        self._sent.append(("buttons", body, [b["id"] for b in buttons]))

    async def send_interactive_list(self, *a, **k):
        sections = k.get("sections")
        if sections is None and len(a) >= 4:
            sections = a[3]
        self._sent.append(("list", sections))


class FakeConv:
    def __init__(self):
        self.states: list = []
        self.messages: list = []

    def set_state(self, conversation_id, state, pending_memo_id=None, pending_artifact_ids=None):
        self.states.append(
            {
                "state": state,
                "pending_memo_id": pending_memo_id,
                "pending_artifact_ids": pending_artifact_ids,
            }
        )

    def add_message(self, *a, **k):
        self.messages.append((a, k))


@pytest.mark.asyncio
async def test_action_card_splits_then_buttons(monkeypatch):
    sent = []
    preview = _contact_preview(
        proposed_updates=[
            ProposedUpdate(
                object_type="contacts",
                field_name="jobtitle",
                field_label="Cargo",
                new_value="X" * 5000,
                current_value="",
                extraction_confidence=0.9,
            ),
        ]
    )
    from app.services.whatsapp.processor_actions import send_action_card

    await send_action_card(
        wa_client=FakeWA(sent),
        msg=_msg(),
        preview=preview,
        conv_svc=FakeConv(),
        conversation_id=uuid4(),
        memo_id=str(uuid4()),
        artifacts={"skip_deal": True, "selected_deal_id": None},
        next_steps=["Llamar a Aritzel"],
    )
    assert sent, "expected outbound sends"
    assert sent[-1][0] == "buttons"
    assert ACT_APPROVE in sent[-1][2]
    assert all(c[0] != "buttons" or len(c[1]) <= 1024 for c in sent)
    assert any(c[0] == "text" for c in sent)
    assert sent[-1][0] == "buttons"


@pytest.mark.asyncio
async def test_retarget_sends_list_with_skip_deal(monkeypatch):
    sent = []
    from app.services.whatsapp.processor_actions import handle_retarget

    await handle_retarget(
        wa_client=FakeWA(sent),
        msg=_msg(),
        conv_svc=FakeConv(),
        conversation_id=uuid4(),
        memo_id=str(uuid4()),
        artifacts={
            "deal_options": [{"deal_id": "d1", "deal_name": "Acme"}],
            "selected_deal_id": None,
        },
        button_id=ACT_RETARGET,
    )
    list_calls = [c for c in sent if c[0] == "list"]
    assert list_calls
    rows = [r for s in (list_calls[-1][1] or []) for r in s.get("rows", [])]
    assert any(r["id"] == PICK_SKIP_DEAL for r in rows)


@pytest.mark.asyncio
async def test_pick_skip_deal_sets_artifacts(monkeypatch):
    from app.services.whatsapp.processor_actions import preview_kwargs_for_pick
    from app.services.whatsapp.processor import _send_preview_for_selection

    kwargs = preview_kwargs_for_pick(PICK_SKIP_DEAL)
    assert kwargs["skip_deal"] is True
    assert kwargs["selected_deal_id"] is None

    captured = {}
    preview = _contact_preview()

    async def fake_build(*a, **k):
        captured["build"] = k
        return preview, "HubSpot", "conn-1", []

    monkeypatch.setattr(
        "app.services.whatsapp.processor._build_preview_for_selection",
        fake_build,
    )
    conv = FakeConv()
    await _send_preview_for_selection(
        None,
        _msg(),
        FakeWA([]),
        "user-1",
        conv,
        uuid4(),
        str(uuid4()),
        selected_deal_id=kwargs["selected_deal_id"],
        skip_deal=kwargs["skip_deal"],
    )
    artifacts = conv.states[-1]["pending_artifact_ids"]
    assert artifacts["skip_deal"] is True
    assert artifacts["selected_deal_id"] is None
    assert captured["build"].get("skip_deal") is True
