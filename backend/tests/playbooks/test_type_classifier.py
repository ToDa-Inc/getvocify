import json
from unittest.mock import patch

from app.services.intelligence.call_reading import build_reading_messages, shape_reading
from app.services.playbooks import type_classifier as tc

TURNS = [{"speaker": "S1", "text": "Hola, te llamo de Vocify"}, {"speaker": "S2", "text": "Dime"}]
PLAYBOOKS = {"discovery": "Cold call", "closing": "Demo de producto", "internal": "Internal"}


# --- the call reading names the playbook in the same pass -----------------------------------

def test_the_reading_is_given_the_companys_types_and_names_one():
    payload = json.loads(build_reading_messages(TURNS, captured_at="2026-10-02", playbooks=PLAYBOOKS)[1]["content"])
    assert [p["key"] for p in payload["playbooks"]] == ["discovery", "closing", "internal"]
    assert shape_reading({"call_type": "cold_first_contact", "playbook": "discovery"}, TURNS, PLAYBOOKS)["playbook"] == "discovery"


def test_unknown_a_type_the_company_does_not_have_or_no_types_name_nothing():
    assert shape_reading({"playbook": "unknown"}, TURNS, PLAYBOOKS)["playbook"] is None
    assert shape_reading({"playbook": "negotiation"}, TURNS, PLAYBOOKS)["playbook"] is None
    assert shape_reading({"playbook": "discovery"}, TURNS, None)["playbook"] is None
    payload = json.loads(build_reading_messages(TURNS, captured_at="2026-10-02")[1]["content"])
    assert "playbooks" not in payload


def test_the_reading_only_offers_published_types_plus_internal():
    motions = {"discovery": "published", "closing": "draft", "internal": "published"}
    with patch.object(tc, "_company_types", return_value=(motions, {"discovery": {"label": None}})):
        offered = tc.reading_playbooks("c1")
    assert set(offered) == {"discovery", "internal"}
    assert "Cold call" in offered["discovery"]
    with patch.object(tc, "_company_types", return_value=({"closing": "draft"}, {})):
        assert tc.reading_playbooks("c1") is None


# --- pinning what it named ------------------------------------------------------------------

class _Query:
    def __init__(self, db):
        self.db, self.row = db, None

    def select(self, *_a):
        return self

    def eq(self, *_a):
        return self

    def limit(self, *_a):
        return self

    def update(self, row):
        self.row = row
        return self

    def execute(self):
        if self.row is not None:
            self.db.updates.append(self.row)
        return type("R", (), {"data": [self.db.memo]})()


class _Db:
    def __init__(self, memo):
        self.memo, self.updates = memo, []

    def table(self, _name):
        return _Query(self)


MEMO = {
    "id": "m1",
    "company_id": "c1",
    "sales_motion_key": "closing",
    "pipeline_meta": {"call_source": "Google Meet", "playbook_pin": {"source": "role_default"}},
}


def _apply(memo, playbook, live="v9", stored=None):
    db = _Db(memo)
    with patch("app.services.playbooks.live.live_version_id", return_value=live), \
         patch.object(tc, "_company_types", return_value=({}, stored or {})):
        tc.apply_reading_type(db, "m1", {"call_type": "cold_first_contact", "playbook": playbook})
    return db.updates


def test_what_the_reading_named_wins_over_vocifys_guesses_and_rules_never_move_it():
    from app.services.playbooks.routing import is_repinnable

    [update] = _apply(MEMO, "discovery")
    assert update["sales_motion_key"] == "discovery" and update["playbook_version_id"] == "v9"
    assert update["pipeline_meta"]["playbook_pin"] == {"source": "reading", "changed_from": "closing"}
    assert update["pipeline_meta"]["call_source"] == "Google Meet"
    assert not is_repinnable(update["pipeline_meta"])


def test_a_type_set_by_hand_or_a_rule_the_company_saved_never_moves():
    assert _apply({**MEMO, "pipeline_meta": {"playbook_pin": {"source": "manual"}}}, "discovery") == []
    ruled = {**MEMO, "pipeline_meta": {"playbook_pin": {"source": "rule"}}}
    assert _apply(ruled, "discovery", stored={"closing": {"applies_to": {"role": "ae"}}}) == []
    [update] = _apply(ruled, "discovery", stored={"closing": {"applies_to": None}})
    assert update["sales_motion_key"] == "discovery"


def test_nothing_named_internal_and_unpublished():
    assert _apply(MEMO, None) == []
    db = _Db(MEMO)
    tc.apply_reading_type(db, "m1", None)
    assert db.updates == []
    [update] = _apply(MEMO, "internal", live=None)
    assert update["sales_motion_key"] == "internal" and update["playbook_version_id"] is None
    assert _apply(MEMO, "discovery", live=None) == []
