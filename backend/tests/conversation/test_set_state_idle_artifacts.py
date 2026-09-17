from uuid import uuid4

from app.services.conversation.service import ConversationService


class _Table:
    def __init__(self):
        self.payload = None

    def update(self, data):
        self.payload = data
        return self

    def eq(self, *args, **kwargs):
        del args, kwargs
        return self

    def execute(self):
        return None


class _SB:
    def __init__(self):
        self.table_obj = _Table()

    def table(self, name):
        del name
        return self.table_obj


def test_idle_keeps_artifacts_when_passed():
    sb = _SB()
    ConversationService(sb).set_state(
        uuid4(),
        "idle",
        pending_artifact_ids={"copilot": {"last_contact_id": "c1"}},
    )
    assert sb.table_obj.payload["pending_artifact_ids"]["copilot"]["last_contact_id"] == "c1"
    assert sb.table_obj.payload["pending_memo_id"] is None


def test_idle_without_artifacts_clears():
    sb = _SB()
    ConversationService(sb).set_state(uuid4(), "idle")
    assert sb.table_obj.payload["pending_artifact_ids"] is None
