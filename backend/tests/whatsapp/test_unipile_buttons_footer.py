import pytest

from app.services.whatsapp.actions import (
    ACT_APPROVE,
    ACT_KEEP,
    ACT_RETARGET,
    PRIMARY_BUTTONS,
    choice_to_action,
)


def test_choice_to_action_maps_primary_buttons():
    assert choice_to_action(1) == ACT_APPROVE
    assert choice_to_action(2) == ACT_KEEP
    assert choice_to_action(3) == ACT_RETARGET
    assert choice_to_action(4) is None


@pytest.mark.asyncio
async def test_unipile_footer_mentions_three_actions(monkeypatch):
    from app.services.unipile.client import UnipileClient

    sent = {}

    async def fake_send(self, to, text, **k):
        sent["text"] = text

    monkeypatch.setattr(UnipileClient, "send_text", fake_send)
    c = UnipileClient()
    await c.send_interactive_buttons(
        "1", "body", PRIMARY_BUTTONS, chat_id="c", account_id="a"
    )
    t = sent["text"].lower()
    assert "1" in t and "2" in t and "3" in t
    assert "add fields" not in t
