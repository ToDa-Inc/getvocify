from app.services.conversation.intent import resolve_intent_by_rules


def test_keep_and_skip_and_change_deal():
    assert resolve_intent_by_rules("no actualizar", "waiting_approval", "m1").intent == "keep"
    assert resolve_intent_by_rules("quita el deal", "waiting_approval", "m1").intent == "skip_deal"
    assert resolve_intent_by_rules("sin deal", "waiting_approval", "m1").intent == "skip_deal"
    assert resolve_intent_by_rules("otro deal", "waiting_approval", "m1").intent == "change_deal"
    r = resolve_intent_by_rules("el deal de acme", "waiting_approval", "m1")
    assert r.intent == "search_deal"
    assert "acme" in (r.params or {}).get("q", "").lower()
