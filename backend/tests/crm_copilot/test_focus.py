from datetime import datetime, timedelta, timezone

import pytest

from app.services.crm_copilot.loop import expire_stale_focus
from app.services.crm_copilot.route import is_focus_switch
from app.services.crm_copilot.tools import execute_tool

from tests.crm_copilot.test_inspect_record import _ctx, _hs


def test_focus_switch_phrases():
    assert is_focus_switch("otro deal")
    assert is_focus_switch("cambia de contacto")
    assert is_focus_switch("ahora hablemos de Acme")
    assert not is_focus_switch("qué deal hemos agendado hoy")
    assert not is_focus_switch("qué pasó con Marc")


def test_expire_stale_focus_keeps_memory():
    copilot = {
        "last_contact_id": "c1",
        "last_deal_id": "d1",
        "memory": ["seller prefers Spanish"],
        "messages": [{"role": "user", "content": "old"}],
        "focus_at": (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(),
    }
    expire_stale_focus(copilot)
    assert "last_contact_id" not in copilot
    assert "last_deal_id" not in copilot
    assert copilot["memory"] == ["seller prefers Spanish"]
    assert copilot["messages"]


def test_fresh_focus_survives():
    copilot = {
        "last_contact_id": "c1",
        "focus_at": datetime.now(timezone.utc).isoformat(),
    }
    expire_stale_focus(copilot)
    assert copilot["last_contact_id"] == "c1"


@pytest.mark.asyncio
async def test_search_clears_previous_deal_focus():
    ctx = _ctx(_hs(), {"last_contact_id": "old", "last_deal_id": "d9", "last_deal_url": "https://hs/d9"})
    await execute_tool("search_contacts", {"query": "Acme"}, ctx)
    copilot = ctx.artifacts["copilot"]
    assert "last_deal_id" not in copilot
    assert "last_deal_url" not in copilot
    assert copilot.get("last_contact_id") != "old"
