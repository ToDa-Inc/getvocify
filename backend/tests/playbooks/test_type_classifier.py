import asyncio
from unittest.mock import patch

from app.services.playbooks import type_classifier as tc


class _Query:
    def __init__(self, db, table):
        self.db, self.table = db, table
        self.update_row = None

    def select(self, *_a):
        return self

    def eq(self, *_a):
        return self

    def neq(self, *_a):
        return self

    def limit(self, *_a):
        return self

    def update(self, row):
        self.update_row = row
        return self

    def execute(self):
        if self.update_row is not None:
            self.db.updates.append(self.update_row)
            return type("R", (), {"data": [self.update_row]})()
        return type("R", (), {"data": list(self.db.rows.get(self.table, []))})()


class _Db:
    def __init__(self, memo):
        self.rows = {"memos": [memo]}
        self.updates = []

    def table(self, name):
        return _Query(self, name)


class _Jev:
    is_available = True

    def __init__(self, answer):
        self.answer = answer
        self.asked = None

    async def classify_choice(self, state, name, instructions, criteria):
        self.asked = {"state": state, "criteria": criteria}
        return self.answer


PUBLISHED = [{"key": "discovery", "label": None}, {"key": "closing", "label": "Demo de producto"}]
MEMO = {
    "id": "m1",
    "company_id": "c1",
    "user_id": "u1",
    "interaction_kind": "meeting",
    "sales_motion_key": "closing",
    "pipeline_meta": {"call_source": "Google Meet", "playbook_pin": {"source": "role_default"}},
}


def _classify(memo, answer):
    jev = _Jev(answer)
    with patch.object(tc, "published_types", return_value=PUBLISHED), \
         patch("app.services.playbooks.routing.contact_status", return_value="new"), \
         patch("app.services.company.sales_role_for_user", return_value=None):
        result = asyncio.run(tc.classify_memo_type(_Db(memo), "m1", "Hola, te llamo de Vocify…", jev=jev))
    return result, jev


def test_jev_chooses_among_published_types_internal_and_unknown_with_the_call_context():
    result, jev = _classify(MEMO, ("discovery", 0.91))
    assert result == ("discovery", 0.91)
    assert set(jev.asked["criteria"]) == {"discovery", "closing", "internal", "unknown"}
    assert "Cold call" in jev.asked["criteria"]["discovery"]
    assert jev.asked["criteria"]["closing"].startswith("Demo de producto")
    assert jev.asked["state"]["app"] == "Google Meet"
    assert jev.asked["state"]["contact_history"] == "new"
    assert jev.asked["state"]["rep_role"] == "unknown"


def test_voice_notes_are_not_typed():
    result, jev = _classify({**MEMO, "interaction_kind": "voice_note"}, ("discovery", 0.9))
    assert result is None and jev.asked is None


def _apply(memo, answer, live="v9"):
    db = _Db(memo)
    with patch("app.services.playbooks.live.live_version_id", return_value=live):
        tc.apply_memo_type(db, "m1", answer)
    return db.updates


def test_a_confident_answer_wins_over_the_rules_and_is_not_moved_by_them_later():
    from app.services.playbooks.routing import is_repinnable

    [update] = _apply(MEMO, ("discovery", 0.88))
    assert update["sales_motion_key"] == "discovery" and update["playbook_version_id"] == "v9"
    assert update["pipeline_meta"]["playbook_pin"] == {"source": "jev", "confidence": 0.88, "changed_from": "closing"}
    assert update["pipeline_meta"]["call_source"] == "Google Meet"
    assert not is_repinnable(update["pipeline_meta"])


def test_a_type_set_by_hand_never_moves():
    manual = {**MEMO, "pipeline_meta": {"playbook_pin": {"source": "manual"}}}
    assert _apply(manual, ("discovery", 0.99)) == []


def test_unknown_or_unsure_leaves_the_rule_pin():
    assert _apply(MEMO, ("unknown", 0.95)) == []
    assert _apply(MEMO, ("discovery", 0.6)) == []
    assert _apply(MEMO, None) == []


def test_internal_needs_no_playbook_and_a_type_without_a_live_version_is_skipped():
    [update] = _apply(MEMO, ("internal", 0.9), live=None)
    assert update["sales_motion_key"] == "internal" and update["playbook_version_id"] is None
    assert _apply(MEMO, ("discovery", 0.9), live=None) == []


def test_long_conversations_keep_their_opening_and_their_end():
    text = "a" * 9000 + "MIDDLE" + "z" * 5000
    excerpt = tc.conversation_excerpt(text)
    assert excerpt.startswith("a" * 100) and excerpt.endswith("z" * 100) and "MIDDLE" not in excerpt


def test_a_rule_the_company_saved_stays_but_a_catalog_default_is_ours_to_replace():
    ruled = {**MEMO, "pipeline_meta": {"playbook_pin": {"source": "rule"}}}
    with patch.object(tc, "_company_types", return_value=({}, {"closing": {"applies_to": {"role": "ae"}}})):
        assert _apply(ruled, ("discovery", 0.95)) == []
    with patch.object(tc, "_company_types", return_value=({}, {"closing": {"applies_to": None}})):
        [update] = _apply(ruled, ("discovery", 0.95))
    assert update["sales_motion_key"] == "discovery"
