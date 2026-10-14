"""Live help reads the whole company's playbook: the call type's own answers first, then the others'."""

from app.services.copilot import load_grounding
from app.services.copilot.grounding import with_company_answers

DEMO = {"sales_motion_key": "closing", "version_id": "v-demo", "steps": [{"id": "s1"}], "entries": [
    {"entry_id": "objection:price", "category": "price", "guidance": "Precio en la demo."},
]}
PROPOSAL = {"sales_motion_key": "negotiation", "version_id": "v-prop", "steps": [{"id": "p1"}], "entries": [
    {"entry_id": "objection:price", "category": "price", "guidance": "Precio en la propuesta."},
    {"entry_id": "objection:custom:upfront", "category": "custom", "label": "No pago por adelantado", "guidance": "Hitos."},
    {"entry_id": "objection:custom:sin_respuesta", "category": "custom", "label": "Legal", "guidance": ""},
]}


def test_a_demo_also_has_the_proposals_answers_and_keeps_its_own():
    merged = with_company_answers(DEMO, [PROPOSAL, DEMO])
    ids = [e["entry_id"] for e in merged["entries"]]
    assert ids == ["objection:price", "objection:custom:upfront"]
    assert merged["entries"][0]["guidance"] == "Precio en la demo."  # the call type's own answer wins
    assert merged["entries"][1]["from_type"] == "negotiation"
    assert merged["steps"] == DEMO["steps"] and merged["version_id"] == "v-demo"  # steps stay the call type's
    assert DEMO["entries"] == [{"entry_id": "objection:price", "category": "price", "guidance": "Precio en la demo."}]


def test_nothing_to_add_and_no_playbook_are_left_alone():
    assert with_company_answers(DEMO, [DEMO]) is DEMO
    assert with_company_answers(None, [PROPOSAL]) is None


def test_a_failed_read_of_the_other_playbooks_is_the_call_types_alone(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("database down")

    monkeypatch.setattr(load_grounding, "live_snapshots", boom)
    assert load_grounding.whole_playbook(object(), "co-1", DEMO) is DEMO
    monkeypatch.setattr(load_grounding, "live_snapshots", lambda *_a, **_k: [DEMO, PROPOSAL])
    assert len(load_grounding.whole_playbook(object(), "co-1", DEMO)["entries"]) == 2
