from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.models.approval import ApprovalPreview, ContactMatch, DealMatch, ProposedUpdate
from app.models.conversation import Conversation, ConversationState
from app.models.memo import MemoExtraction
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

    def get_last_messages(self, conversation_id, limit=10):
        return []

    def is_state_expired(self, state):
        return False


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


def _deal(**overrides) -> DealMatch:
    data = dict(
        deal_id="d1",
        deal_name="Acme Renewal",
        last_updated="2026-01-01",
        match_confidence=0.8,
        match_reason="name",
    )
    data.update(overrides)
    return DealMatch(**data)


class _ExtractConv(FakeConv):
    def __init__(self, conversation: Conversation):
        super().__init__()
        self._conversation = conversation

    def get_or_create_conversation(self, **k):
        return self._conversation

    def get_state(self, conversation_id):
        return None

    def is_state_expired(self, state):
        return False


async def _run_extract_path(monkeypatch, matches: list[DealMatch], sent: list) -> dict:
    from app.services.whatsapp.processor import WhatsAppAccount, process_whatsapp_message

    captured: dict = {}
    memo_id = str(uuid4())
    now = datetime.now(timezone.utc)
    conversation = Conversation(
        id=uuid4(),
        chat_id="phone:34600111222",
        account_id="meta",
        user_id=uuid4(),
        channel="whatsapp",
        created_at=now,
        updated_at=now,
    )
    conv_svc = _ExtractConv(conversation)
    extraction = MemoExtraction(
        companyName="Acme",
        contactName="Ana",
        summary="Visited Ana at Acme about the renewal today",
    )

    async def fake_account(*a, **k):
        return WhatsAppAccount(
            user_id="user-1",
            profile={"id": "user-1", "company_name": "Vocify"},
            crm_connection={"id": "conn-1", "provider": "hubspot", "status": "connected"},
        )

    async def fake_extract(*a, **k):
        return memo_id, extraction

    async def fake_find(*a, **k):
        return matches, "conn-1", "hubspot"

    async def fake_build(*a, **k):
        captured["build"] = k
        return _contact_preview(), "HubSpot", "conn-1", [m.model_dump() for m in matches]

    monkeypatch.setattr("app.services.whatsapp.processor.resolve_whatsapp_account", fake_account)
    monkeypatch.setattr("app.services.whatsapp.processor.ConversationService", lambda *a, **k: conv_svc)
    monkeypatch.setattr("app.services.whatsapp.processor._extract_and_create_memo", fake_extract)
    monkeypatch.setattr("app.services.whatsapp.processor._find_candidate_deals", fake_find)
    monkeypatch.setattr("app.services.whatsapp.processor._build_preview_for_selection", fake_build)

    msg = IncomingMessage(
        message_id="wamid.extract",
        from_phone="34600111222",
        timestamp="1",
        type="text",
        text="Visited Ana at Acme about the renewal today",
    )
    await process_whatsapp_message(None, msg, FakeWA(sent))
    captured["conv"] = conv_svc
    captured["memo_id"] = memo_id
    return captured


@pytest.mark.asyncio
async def test_extract_path_does_not_send_numbered_deal_list_first(monkeypatch):
    sent = []
    captured = await _run_extract_path(
        monkeypatch,
        [
            _deal(deal_id="d1", deal_name="Acme Renewal", match_confidence=0.8),
            _deal(deal_id="d2", deal_name="Acme New", match_confidence=0.75),
        ],
        sent,
    )
    interactives = [c for c in sent if c[0] in ("buttons", "list")]
    assert interactives, f"expected action card, got {sent}"
    assert interactives[0][0] == "buttons"
    assert ACT_APPROVE in interactives[0][2]
    assert all(c[0] != "list" for c in sent)
    assert all(
        c[0] != "text" or "Choose where this update should go" not in c[1]
        for c in sent
    )
    assert captured["build"].get("skip_deal") is True
    assert not captured["build"].get("selected_deal_id")
    states = captured["conv"].states
    assert states
    assert states[-1]["state"] != "waiting_deal_choice"


@pytest.mark.asyncio
async def test_extract_path_does_not_auto_apply_high_confidence_deal(monkeypatch):
    sent = []
    captured = await _run_extract_path(
        monkeypatch,
        [_deal(deal_id="d1", match_confidence=0.99)],
        sent,
    )
    interactives = [c for c in sent if c[0] in ("buttons", "list")]
    assert interactives
    assert interactives[0][0] == "buttons"
    assert ACT_APPROVE in interactives[0][2]
    assert captured["build"].get("skip_deal") is True
    assert not captured["build"].get("selected_deal_id")


class FakeWANoList:
    def __init__(self, sent: list):
        self._sent = sent

    def is_configured(self):
        return True

    async def send_text(self, to, text, **k):
        self._sent.append(("text", text))

    async def send_interactive_buttons(self, to, body, buttons, **k):
        self._sent.append(("buttons", body, [b["id"] for b in buttons]))


class _ApprovalConv(FakeConv):
    def __init__(self, conversation: Conversation, state: ConversationState):
        super().__init__()
        self._conversation = conversation
        self._state = state

    def get_or_create_conversation(self, **k):
        return self._conversation

    def get_state(self, conversation_id):
        return self._state


async def _run_waiting_approval(monkeypatch, text: str) -> list[str]:
    from app.services.whatsapp.processor import WhatsAppAccount, process_whatsapp_message

    calls: list[str] = []

    async def fake_approve(*a, **k):
        calls.append("approve")

    async def fake_reject(*a, **k):
        calls.append("keep")

    async def fake_retarget(*a, **k):
        calls.append("retarget")

    async def fake_add(*a, **k):
        calls.append("edit")
        return True

    monkeypatch.setattr("app.services.whatsapp.processor._approve_pending_memo", fake_approve)
    monkeypatch.setattr("app.services.whatsapp.processor._reject_pending_memo", fake_reject)
    monkeypatch.setattr("app.services.whatsapp.processor._retarget_with_options", fake_retarget)
    monkeypatch.setattr("app.services.whatsapp.processor._handle_waiting_add_fields", fake_add)

    now = datetime.now(timezone.utc)
    conversation = Conversation(
        id=uuid4(),
        chat_id="phone:34600111222",
        account_id="meta",
        user_id=uuid4(),
        channel="whatsapp",
        created_at=now,
        updated_at=now,
    )
    state = ConversationState(
        conversation_id=conversation.id,
        state="waiting_approval",
        pending_memo_id=uuid4(),
        pending_artifact_ids={"skip_deal": True},
        updated_at=now,
    )
    conv_svc = _ApprovalConv(conversation, state)

    async def fake_account(*a, **k):
        return WhatsAppAccount(
            user_id="user-1",
            profile={"id": "user-1"},
            crm_connection={"id": "conn-1", "provider": "hubspot", "status": "connected"},
        )

    monkeypatch.setattr("app.services.whatsapp.processor.resolve_whatsapp_account", fake_account)
    monkeypatch.setattr("app.services.whatsapp.processor.ConversationService", lambda *a, **k: conv_svc)

    msg = IncomingMessage(
        message_id="wamid.approval",
        from_phone="34600111222",
        timestamp="1",
        type="text",
        text=text,
    )
    await process_whatsapp_message(None, msg, FakeWA([]))
    return calls


@pytest.mark.asyncio
async def test_waiting_approval_bare_2_keeps(monkeypatch):
    assert await _run_waiting_approval(monkeypatch, "2") == ["keep"]


@pytest.mark.asyncio
async def test_waiting_approval_amount_2_edits_not_reject(monkeypatch):
    calls = await _run_waiting_approval(monkeypatch, "amount: 2")
    assert "edit" in calls
    assert "keep" not in calls


@pytest.mark.asyncio
async def test_waiting_approval_bare_1_and_3_map_through_choice_to_action(monkeypatch):
    assert await _run_waiting_approval(monkeypatch, "1") == ["approve"]
    calls = await _run_waiting_approval(monkeypatch, "3")
    assert calls[-1] == "retarget"


@pytest.mark.asyncio
async def test_ambiguous_contact_stores_picks_when_list_sends(monkeypatch):
    sent = []
    conv = FakeConv()
    preview = _contact_preview(
        selected_contact=None,
        contact_candidates=[
            ContactMatch(contact_id="c1", name="Ana López"),
            ContactMatch(contact_id="c2", name="Bob"),
        ],
    )
    from app.services.whatsapp.processor_actions import PICK_CONTACT_PREFIX, send_action_card

    await send_action_card(
        wa_client=FakeWA(sent),
        msg=_msg(),
        preview=preview,
        conv_svc=conv,
        conversation_id=uuid4(),
        memo_id=str(uuid4()),
        artifacts={"skip_deal": True},
    )
    artifacts = conv.states[-1]["pending_artifact_ids"]
    assert conv.states[-1]["state"] == "waiting_retarget"
    assert artifacts["retarget_picks"] == [
        f"{PICK_CONTACT_PREFIX}c1",
        f"{PICK_CONTACT_PREFIX}c2",
    ]
    assert any(c[0] == "list" for c in sent)


@pytest.mark.asyncio
async def test_ambiguous_contact_numbered_fallback_without_list(monkeypatch):
    sent = []
    conv = FakeConv()
    preview = _contact_preview(
        selected_contact=None,
        contact_candidates=[
            ContactMatch(contact_id="c1", name="Ana López"),
            ContactMatch(contact_id="c2", name="Bob"),
        ],
    )
    from app.services.whatsapp.processor_actions import PICK_CONTACT_PREFIX, send_action_card

    await send_action_card(
        wa_client=FakeWANoList(sent),
        msg=_msg(),
        preview=preview,
        conv_svc=conv,
        conversation_id=uuid4(),
        memo_id=str(uuid4()),
        artifacts={"skip_deal": True},
    )
    artifacts = conv.states[-1]["pending_artifact_ids"]
    assert artifacts["retarget_picks"] == [
        f"{PICK_CONTACT_PREFIX}c1",
        f"{PICK_CONTACT_PREFIX}c2",
    ]
    texts = [c[1] for c in sent if c[0] == "text"]
    assert texts
    assert "1. Ana López" in texts[-1]
    assert "2. Bob" in texts[-1]
    assert not any(c[0] == "list" for c in sent)
