from datetime import datetime, timezone
from uuid import uuid4

from app.models.conversation import ConversationState
from app.services.crm_copilot.route import should_handle_with_copilot


def _state(state="idle", artifacts=None, memo=None):
    return ConversationState(
        conversation_id=uuid4(),
        state=state,
        pending_memo_id=memo,
        pending_artifact_ids=artifacts,
        updated_at=datetime.now(timezone.utc),
    )


def test_idle_and_none_use_copilot():
    assert should_handle_with_copilot(None) is True
    assert should_handle_with_copilot(_state("idle")) is True


def test_legacy_memo_approval_stays_on_fsm():
    assert (
        should_handle_with_copilot(
            _state("waiting_approval", artifacts={"skip_deal": True}, memo=uuid4())
        )
        is False
    )


def test_copilot_pending_uses_copilot_legacy_retarget_does_not():
    assert should_handle_with_copilot(
        _state("waiting_approval", artifacts={"copilot": {"pending_tool": "apply_write"}})
    )
    assert should_handle_with_copilot(
        _state("waiting_retarget", artifacts={"copilot": {"choices": [{"id": "pick:contact:1", "label": "Marc"}]}})
    )
    assert should_handle_with_copilot(_state("waiting_retarget", artifacts={})) is False
    assert (
        should_handle_with_copilot(
            _state("waiting_retarget", artifacts={"deal_options": [{"deal_id": "d1"}]})
        )
        is False
    )
