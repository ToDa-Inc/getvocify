from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.models.conversation import Conversation, ConversationState
from app.services.crm_copilot.loop import CopilotTurnResult
from app.services.whatsapp.actions import ACT_APPROVE, ACT_KEEP
from app.services.whatsapp.processor import WhatsAppAccount, _emit_copilot_turn, process_whatsapp_message
from app.services.whatsapp.webhook_parser import IncomingMessage

from tests.whatsapp.test_processor_retarget import FakeConv, FakeWA, _ExtractConv, _msg


@pytest.mark.asyncio
async def test_emit_confirm_is_one_button_bubble_not_actualizar_or():
    sent = []
    result = CopilotTurnResult(
        kind="confirm",
        text="Nota: Les encaja la solución para sus comerciales de calle.",
        state="waiting_approval",
        artifacts={"copilot": {}},
    )
    conv = FakeConv()
    await _emit_copilot_turn(FakeWA(sent), _msg(), conv, uuid4(), result)
    assert len(sent) == 1
    assert sent[0][0] == "buttons"
    assert sent[0][1].startswith("Nota:")
    assert sent[0][2] == [ACT_APPROVE, ACT_KEEP]
    assert "Actualizar or No actualizar" not in sent[0][1]


@pytest.mark.asyncio
async def test_audio_copilot_gets_plain_transcript_not_voice_prefix(monkeypatch):
    seen = []

    async def fake_account(*a, **k):
        return WhatsAppAccount(
            user_id="user-1",
            profile={"id": "user-1"},
            crm_connection={"id": "conn-1", "provider": "hubspot", "status": "connected"},
        )

    async def fake_transcribe(*a, **k):
        return "Les encaja la solución para sus comerciales de calle", None

    async def fake_turn(user_text, **k):
        seen.append(user_text)
        return CopilotTurnResult(kind="text", text="ok", artifacts={"copilot": {}})

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
    monkeypatch.setattr("app.services.whatsapp.processor.resolve_whatsapp_account", fake_account)
    monkeypatch.setattr("app.services.whatsapp.processor.ConversationService", lambda *a, **k: conv_svc)
    monkeypatch.setattr("app.services.whatsapp.processor._transcribe_audio", fake_transcribe)
    monkeypatch.setattr("app.services.whatsapp.processor.run_copilot_turn", fake_turn)

    sent = []
    msg = IncomingMessage(
        message_id="wamid.audio1",
        from_phone="34600111222",
        timestamp="1",
        type="audio",
        audio_id="media.1",
    )
    await process_whatsapp_message(None, msg, FakeWA(sent))
    assert seen == ["Les encaja la solución para sus comerciales de calle"]


@pytest.mark.asyncio
async def test_voice_retry_while_confirm_pending_is_ignored(monkeypatch):
    turns = []
    sent = []

    async def fake_account(*a, **k):
        return WhatsAppAccount(
            user_id="user-1",
            profile={"id": "user-1"},
            crm_connection={"id": "conn-1", "provider": "hubspot", "status": "connected"},
        )

    async def fake_transcribe(*a, **k):
        return "Les encaja la solución para sus comerciales de calle", None

    async def fake_turn(user_text, **k):
        turns.append(user_text)
        return CopilotTurnResult(kind="confirm", text="should not emit", artifacts={"copilot": {}})

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

    class PendingConv(_ExtractConv):
        def get_state(self, conversation_id):
            return ConversationState(
                conversation_id=conversation.id,
                state="waiting_approval",
                pending_artifact_ids={
                    "copilot": {
                        "pending_tool": "create_note",
                        "pending_args": {"body": "x"},
                        "messages": [{"role": "user", "content": "Les encaja la solución para sus comerciales de calle"}],
                    }
                },
                updated_at=now,
            )

    conv_svc = PendingConv(conversation)
    monkeypatch.setattr("app.services.whatsapp.processor.resolve_whatsapp_account", fake_account)
    monkeypatch.setattr("app.services.whatsapp.processor.ConversationService", lambda *a, **k: conv_svc)
    monkeypatch.setattr("app.services.whatsapp.processor._transcribe_audio", fake_transcribe)
    monkeypatch.setattr("app.services.whatsapp.processor.run_copilot_turn", fake_turn)

    msg = IncomingMessage(
        message_id="wamid.audio-retry",
        from_phone="34600111222",
        timestamp="1",
        type="audio",
        audio_id="media.1",
    )
    await process_whatsapp_message(None, msg, FakeWA(sent))
    assert turns == []
    assert sent == []
