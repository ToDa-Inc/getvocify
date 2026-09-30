"""T8: routing at pin time (playbook_fields_for_capture) and the re-pin before C04."""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")

import pytest

from app.config import settings
from app.services import feature_flags
from app.services.captures import playbook_fields_for_capture
from app.services.playbooks import routing
from app.services.playbooks.routing import repin_before_c04
from tests.playbooks.live_double import live_view_rows


@pytest.fixture(autouse=True)
def _flags(monkeypatch):
    feature_flags.clear_cache()
    monkeypatch.setattr(settings, "SALES_ROLES_ENABLED", True)
    monkeypatch.setattr(settings, "PLAYBOOK_ROUTING_ENABLED", True)
    yield
    feature_flags.clear_cache()


class _Query:
    def __init__(self, db, name):
        self.db, self.name = db, name
        self.filters: list[tuple[str, str, object]] = []
        self.patch = None
        self.max = None

    def select(self, *_a, **_k):
        return self

    def update(self, patch):
        self.patch = patch
        return self

    def eq(self, column, value):
        self.filters.append(("eq", column, value))
        return self

    def neq(self, column, value):
        self.filters.append(("neq", column, value))
        return self

    def limit(self, n):
        self.max = n
        return self

    def execute(self):
        if self.name in self.db.broken:
            raise RuntimeError(f"{self.name} is down")
        rows = live_view_rows(self.db.tables["playbooks"]) if self.name == "playbooks_live" else self.db.tables.get(self.name, [])
        for op, column, value in self.filters:
            if op == "eq":
                rows = [r for r in rows if str(r.get(column)) == str(value)]
            else:
                rows = [r for r in rows if str(r.get(column)) != str(value)]
        if self.patch is not None:
            for row in rows:
                row.update(self.patch)
            self.db.updates.append((self.name, dict(self.patch)))
        return type("R", (), {"data": rows[: self.max] if self.max else rows})()


class _Rpc:
    def __init__(self, db):
        self.db = db

    def execute(self):
        rows = [
            {"sales_motion_key": p["sales_motion_key"], "motion_status": "published" if p.get("active_version_id") else "missing"}
            for p in self.db.tables["playbooks"]
            if p["company_id"] == "co-1"
        ]
        return type("R", (), {"data": rows})()


class _Db:
    def __init__(self, *, published=(), rules=None, memos=None, broken=()):
        rules = rules or {}
        self.tables = {
            "playbooks": [
                {
                    "id": f"pb-{key}",
                    "company_id": "co-1",
                    "sales_motion_key": key,
                    "active_version_id": f"v-{key}" if key in published else None,
                    "label": None,
                    "applies_to": rules.get(key),
                }
                for key in dict.fromkeys(list(published) + list(rules))
            ],
            "memos": list(memos or []),
            "crm_connections": [],
            "company_feature_flags": [],
        }
        self.broken = set(broken)
        self.updates: list = []

    def table(self, name):
        return _Query(self, name)

    def rpc(self, name, _params=None):
        assert name == "list_playbook_motions"
        return _Rpc(self)


ALL = ("discovery", "inbound", "ae_discovery", "closing", "negotiation")


def _pin(db, **kwargs):
    kwargs.setdefault("interaction_kind", "meeting")
    return playbook_fields_for_capture(db, "co-1", **kwargs)


def _prior(contact="c-1", deal=None, status="pending_review"):
    return {"id": "old", "company_id": "co-1", "hubspot_contact_id": contact, "hubspot_deal_id": deal, "status": status}


# -- pin time --------------------------------------------------------------------------------


def test_first_meeting_of_a_contact_pins_ae_discovery_and_marks_the_source():
    fields = _pin(_Db(published=ALL), sales_role="ae", hubspot_contact_id="c-1")
    assert fields == {
        "sales_motion_key": "ae_discovery",
        "playbook_version_id": "v-ae_discovery",
        "pipeline_meta": {"playbook_pin": {"source": "rule"}},
    }


def test_a_contact_with_an_earlier_memo_gets_the_role_default():
    fields = _pin(_Db(published=ALL, memos=[_prior()]), sales_role="ae", hubspot_contact_id="c-1")
    assert fields["sales_motion_key"] == "closing"
    assert fields["pipeline_meta"] == {"playbook_pin": {"source": "rule"}}  # closing's own rule matched


def test_an_earlier_memo_on_the_same_deal_counts_and_a_failed_one_does_not():
    db = _Db(published=ALL, memos=[_prior(contact="c-9", deal="d-1")])
    assert _pin(db, sales_role="ae", hubspot_contact_id="c-1", hubspot_deal_id="d-1")["sales_motion_key"] == "closing"
    failed = _Db(published=ALL, memos=[_prior(status="failed")])
    assert _pin(failed, sales_role="ae", hubspot_contact_id="c-1")["sales_motion_key"] == "ae_discovery"


def test_without_a_contact_or_deal_the_new_contact_rule_cannot_match_so_it_is_the_role_default():
    fields = _pin(_Db(published=ALL), sales_role="ae")
    assert fields["sales_motion_key"] == "closing"


def test_no_crm_and_a_stage_rule_falls_back_to_the_role_default(monkeypatch):
    rules = {"negotiation": {"role": "ae", "channels": ["meeting"], "contact": "any", "deal_stages": ["proposal"]}}
    db = _Db(published=ALL, rules=rules, memos=[_prior()])
    fields = _pin(db, sales_role="ae", hubspot_contact_id="c-1", hubspot_deal_id="d-1")
    assert fields["sales_motion_key"] == "closing"


def test_a_deal_in_a_configured_stage_pins_negotiation(monkeypatch):
    rules = {"negotiation": {"role": "ae", "channels": ["meeting"], "contact": "any", "deal_stages": ["proposal"]}}
    db = _Db(published=ALL, rules=rules, memos=[_prior(deal="d-1")])
    db.tables["crm_connections"].append({"company_id": "co-1", "provider": "hubspot", "status": "connected"})
    asked = []
    monkeypatch.setattr(routing, "deal_stage_for", lambda connection, deal_id: asked.append(deal_id) or "proposal")
    fields = _pin(db, sales_role="ae", hubspot_contact_id="c-1", hubspot_deal_id="d-1")
    assert fields["sales_motion_key"] == "negotiation"
    assert fields["playbook_version_id"] == "v-negotiation"
    assert asked == ["d-1"]
    # The deal is somewhere else: closing.
    monkeypatch.setattr(routing, "deal_stage_for", lambda connection, deal_id: "qualified")
    assert _pin(db, sales_role="ae", hubspot_contact_id="c-1", hubspot_deal_id="d-1")["sales_motion_key"] == "closing"


def test_the_crm_is_not_asked_when_no_published_rule_depends_on_it(monkeypatch):
    db = _Db(published=("discovery", "closing"))
    db.tables["crm_connections"].append({"company_id": "co-1", "provider": "hubspot", "status": "connected"})

    def boom(*_a):
        raise AssertionError("the CRM must not be called")

    monkeypatch.setattr(routing, "deal_stage_for", boom)
    monkeypatch.setattr(routing, "contact_inbound", boom)
    assert _pin(db, sales_role="ae", hubspot_contact_id="c-1", hubspot_deal_id="d-1")["sales_motion_key"] == "closing"


def test_an_inbound_lead_pins_the_inbound_playbook(monkeypatch):
    db = _Db(published=ALL)
    db.tables["crm_connections"].append({"company_id": "co-1", "provider": "hubspot", "status": "connected"})
    monkeypatch.setattr(routing, "contact_inbound", lambda connection, contact_id: True)
    fields = _pin(db, sales_role="sdr", interaction_kind="call", hubspot_contact_id="c-1")
    assert fields["sales_motion_key"] == "inbound"
    monkeypatch.setattr(routing, "contact_inbound", lambda connection, contact_id: None)
    assert _pin(db, sales_role="sdr", interaction_kind="call", hubspot_contact_id="c-1")["sales_motion_key"] == "discovery"


def test_an_unpublished_rule_never_pins():
    db = _Db(published=("discovery", "closing"), rules={"ae_discovery": None})
    fields = _pin(db, sales_role="ae", hubspot_contact_id="c-1")
    assert fields["sales_motion_key"] == "closing"


def test_role_default_without_a_published_version_is_unchanged():
    # closing not published: the rule would say closing, D5 says closing, nothing pins (as today).
    db = _Db(published=("discovery",))
    assert _pin(db, sales_role="ae", hubspot_contact_id="c-1") == {}


def test_an_explicit_key_is_never_routed():
    db = _Db(published=ALL)
    fields = _pin(db, sales_role="ae", sales_motion_key="closing", hubspot_contact_id="c-1")
    assert fields == {"sales_motion_key": "closing", "playbook_version_id": "v-closing"}


def test_a_failing_memo_lookup_never_blocks_the_capture():
    db = _Db(published=ALL, broken=("memos",))
    fields = _pin(db, sales_role="ae", hubspot_contact_id="c-1", hubspot_deal_id="d-1")
    assert fields["sales_motion_key"] == "closing"
    assert fields["pipeline_meta"] == {"playbook_pin": {"source": "rule", "provisional": True}}


def test_a_failing_crm_lookup_never_blocks_the_capture():
    rules = {"negotiation": {"role": "ae", "channels": ["meeting"], "contact": "any", "deal_stages": ["proposal"]}}
    db = _Db(published=ALL, rules=rules, memos=[_prior()], broken=("crm_connections",))
    fields = _pin(db, sales_role="ae", hubspot_contact_id="c-1", hubspot_deal_id="d-1")
    assert fields["sales_motion_key"] == "closing"
    assert fields["pipeline_meta"] == {"playbook_pin": {"source": "rule", "provisional": True}}


def test_a_broken_rules_read_falls_back_to_todays_pin():
    class Boom(_Db):
        def rpc(self, *_a, **_k):
            raise RuntimeError("rpc down")

    fields = _pin(Boom(published=ALL), sales_role="ae", hubspot_contact_id="c-1")
    assert fields == {
        "sales_motion_key": "closing",
        "playbook_version_id": "v-closing",
        "pipeline_meta": {"playbook_pin": {"source": "role_default"}},
    }


def test_flag_off_is_identical_to_today(monkeypatch):
    monkeypatch.setattr(settings, "PLAYBOOK_ROUTING_ENABLED", False)
    feature_flags.clear_cache()
    db = _Db(published=ALL)
    assert _pin(db, sales_role="ae", hubspot_contact_id="c-1") == {
        "sales_motion_key": "closing",
        "playbook_version_id": "v-closing",
    }
    assert _pin(db, sales_role="sdr", interaction_kind="call") == {
        "sales_motion_key": "discovery",
        "playbook_version_id": "v-discovery",
    }
    assert db.updates == []


def test_sales_roles_flag_off_means_no_routing_at_all(monkeypatch):
    monkeypatch.setattr(settings, "SALES_ROLES_ENABLED", False)
    feature_flags.clear_cache()
    assert _pin(_Db(published=ALL), sales_role="ae", hubspot_contact_id="c-1") == {}


def test_the_pin_says_where_it_came_from_and_whether_something_was_unknown():
    db = _Db(published=ALL, memos=[_prior()])
    # AE meeting with no contact or deal on the capture (Recall, desktop): closing matched,
    # but ae_discovery needed to know whether the contact is new -> provisional.
    unknown = _pin(db, sales_role="ae")
    assert unknown["sales_motion_key"] == "closing"
    assert unknown["pipeline_meta"] == {"playbook_pin": {"source": "rule", "provisional": True}}
    # Everything a rule needed was known: final.
    known = _pin(db, sales_role="ae", hubspot_contact_id="c-1")
    assert known["pipeline_meta"] == {"playbook_pin": {"source": "rule"}}
    # No rule matches an AE call to a known contact: the role default, which can be re-routed.
    call = _pin(db, sales_role="ae", interaction_kind="call", hubspot_contact_id="c-1")
    assert call["sales_motion_key"] == "closing"
    assert call["pipeline_meta"] == {"playbook_pin": {"source": "role_default"}}
    general = _pin(db, sales_role="general", interaction_kind="meeting")
    assert general["pipeline_meta"] == {"playbook_pin": {"source": "role_default"}}


# -- re-pin before C04 -----------------------------------------------------------------------


def _memo(**overrides):
    memo = {
        "id": "m-1",
        "company_id": "co-1",
        "user_id": "u-1",
        "interaction_kind": "meeting",
        "source": "recall",
        "source_type": "recall_bot",
        "sales_motion_key": "closing",
        "playbook_version_id": "v-closing",
        "pipeline_meta": {"playbook_pin": {"source": "role_default"}, "stages": []},
        "hubspot_contact_id": "c-1",
        "hubspot_deal_id": None,
    }
    memo.update(overrides)
    return memo


@pytest.fixture
def ae(monkeypatch):
    monkeypatch.setattr("app.services.company.sales_role_for_user", lambda _s, _u, company_id=None: "ae")


def _db_with_memo(memo, **kwargs):
    db = _Db(published=ALL, **kwargs)
    db.tables["memos"].append(dict(memo))
    return db


def test_a_role_default_pin_moves_to_the_rule_now_that_the_contact_is_known(ae):
    memo = _memo()
    db = _db_with_memo(memo)
    result = repin_before_c04(db, memo)
    assert result["sales_motion_key"] == "ae_discovery"
    assert result["playbook_version_id"] == "v-ae_discovery"
    assert result["pipeline_meta"]["playbook_pin"] == {"source": "rule", "repinned_from": "closing"}
    assert result["pipeline_meta"]["stages"] == []  # other pipeline_meta keys survive
    stored = db.tables["memos"][0]
    assert (stored["sales_motion_key"], stored["playbook_version_id"]) == ("ae_discovery", "v-ae_discovery")


def test_a_provisional_rule_pin_is_routed_again_too(ae):
    """The AE meeting pinned to closing because the contact was unknown at reserve time."""
    memo = _memo(pipeline_meta={"playbook_pin": {"source": "rule", "provisional": True}})
    db = _db_with_memo(memo)
    result = repin_before_c04(db, memo)
    assert result["sales_motion_key"] == "ae_discovery"
    assert result["pipeline_meta"]["playbook_pin"] == {"source": "rule", "repinned_from": "closing"}


def test_the_re_pin_is_idempotent(ae):
    memo = _memo()
    db = _db_with_memo(memo)
    once = repin_before_c04(db, memo)
    updates = len(db.updates)
    twice = repin_before_c04(db, once)
    assert twice == once
    assert len(db.updates) == updates


def test_the_memos_own_row_does_not_count_as_a_prior_memo(ae):
    memo = _memo(id="m-1")
    db = _db_with_memo(memo)  # the only memo of c-1 is this one
    assert repin_before_c04(db, memo)["sales_motion_key"] == "ae_discovery"


def test_a_contact_with_history_stays_on_the_role_default(ae):
    memo = _memo()
    db = _db_with_memo(memo, memos=[_prior()])
    assert repin_before_c04(db, memo) == memo
    assert db.updates == []


def test_the_deal_stage_known_by_now_re_pins_to_negotiation(ae, monkeypatch):
    rules = {"negotiation": {"role": "ae", "channels": ["meeting"], "contact": "any", "deal_stages": ["proposal"]}}
    memo = _memo(hubspot_deal_id="d-1")
    db = _db_with_memo(memo, rules=rules, memos=[_prior(deal="d-1")])
    db.tables["crm_connections"].append({"company_id": "co-1", "provider": "hubspot", "status": "connected"})
    monkeypatch.setattr(routing, "deal_stage_for", lambda connection, deal_id: "proposal")
    assert repin_before_c04(db, memo)["sales_motion_key"] == "negotiation"


@pytest.mark.parametrize(
    "pipeline_meta",
    [
        {"playbook_pin": {"source": "manual"}},
        {"playbook_pin": {"source": "rule"}},
        {"stages": []},  # a pin from before routing: unknown provenance, left alone
        None,
    ],
)
def test_only_a_role_default_pin_is_ever_re_routed(ae, pipeline_meta):
    memo = _memo(pipeline_meta=pipeline_meta)
    db = _db_with_memo(memo)
    assert repin_before_c04(db, memo) == memo
    assert db.updates == []


def test_no_re_pin_when_the_flag_is_off(ae, monkeypatch):
    monkeypatch.setattr(settings, "PLAYBOOK_ROUTING_ENABLED", False)
    feature_flags.clear_cache()
    memo = _memo()
    db = _db_with_memo(memo)
    assert repin_before_c04(db, memo) == memo
    assert db.updates == []


def test_no_re_pin_when_the_new_type_has_no_published_version(ae):
    memo = _memo()
    db = _Db(published=("discovery", "closing"))
    db.tables["memos"].append(dict(memo))
    assert repin_before_c04(db, memo) == memo


def test_a_failure_is_swallowed_and_the_memo_is_returned_as_it_was(ae):
    memo = _memo()
    db = _db_with_memo(memo, broken=("playbooks", "playbooks_live"))
    assert repin_before_c04(db, memo) == memo


def test_the_hook_re_pins_before_c04_is_scheduled(ae, monkeypatch):
    """run_post_extraction_hooks: the pin C04 reads is the new one."""
    from app.services import memo_extraction_hooks
    from app.services.intelligence import extract

    memo = _memo()
    db = _db_with_memo(memo)
    seen = {}

    def fake_schedule(supabase, memo_id, company_id=None):
        seen["pin"] = dict(db.tables["memos"][0])["sales_motion_key"]
        return True

    monkeypatch.setattr(extract, "schedule_intelligence", fake_schedule)
    monkeypatch.setattr(memo_extraction_hooks, "_maybe_insert_meeting_proposal", lambda *a, **k: None)
    monkeypatch.setattr(memo_extraction_hooks, "_ensure_screening_outcome", lambda _s, m: m)
    published = []
    monkeypatch.setattr(memo_extraction_hooks, "_publish_coaching", lambda _s, m, _e: published.append(m["sales_motion_key"]))

    memo_extraction_hooks.run_post_extraction_hooks(db, memo_id="m-1", extraction={"summary": "x"}, memo=memo)
    assert seen["pin"] == "ae_discovery"
