"""T8: motion_for with rules. Pure: precedence, specificity, unknown context, published-only."""

from __future__ import annotations

import pytest

from app.services.playbooks.catalog import default_applies_to
from app.services.playbooks.motion import motion_for, route
from app.services.playbooks.routing import rules_from


def _catalog_rules(published=("discovery", "inbound", "ae_discovery", "closing"), *, stages=None, extra=()):
    """The catalog defaults, every key in `published` published. `stages` = {key: [ids]}."""
    keys = ["discovery", "inbound", "ae_discovery", "closing", "negotiation"]
    out = []
    for key in keys:
        applies_to = default_applies_to(key)
        if stages and key in stages:
            applies_to["deal_stages"] = list(stages[key])
        out.append({"key": key, "applies_to": applies_to, "published": key in published})
    out.extend(extra)
    return out


NEW = {"contact": "new", "inbound": None, "deal_stage": None}
CONTACTED = {"contact": "contacted", "inbound": None, "deal_stage": None}
INBOUND = {"contact": "new", "inbound": True, "deal_stage": None}


# Without rules the signature behaves as it always did.
@pytest.mark.parametrize(
    "role,kind,expected",
    [
        ("sdr", "call", "discovery"),
        ("sdr", "meeting", "discovery"),
        ("ae", "call", "closing"),
        ("ae", "voice_note", "closing"),
        ("general", "call", "discovery"),
        (None, "meeting", "closing"),
        (None, "visit", "closing"),
        ("general", "voice_note", None),
    ],
)
def test_without_rules_it_is_the_role_default(role, kind, expected):
    assert motion_for(role, kind) == expected
    assert motion_for(role, kind, {"contact": "new"}) == expected
    assert motion_for(role, kind, None, []) == expected


@pytest.mark.parametrize(
    "role,kind,context,expected",
    [
        # SDR calls: cold call by default, inbound lead when the CRM says so (3 conditions beat 2).
        ("sdr", "call", NEW, "discovery"),
        ("sdr", "call", CONTACTED, "discovery"),
        ("sdr", "call", None, "discovery"),
        ("sdr", "call", INBOUND, "inbound"),
        ("sdr", "call", {"contact": "contacted", "inbound": True, "deal_stage": None}, "inbound"),
        ("sdr", "call", {"contact": None, "inbound": False, "deal_stage": None}, "discovery"),
        # SDR meeting/visit: no SDR rule covers it, so the role default.
        ("sdr", "meeting", NEW, "discovery"),
        # AE: the first meeting of a deal is discovery; later ones (or an unknown) are demo/close.
        ("ae", "meeting", NEW, "ae_discovery"),
        ("ae", "visit", NEW, "ae_discovery"),
        ("ae", "call", NEW, "ae_discovery"),
        ("ae", "meeting", CONTACTED, "closing"),
        ("ae", "meeting", None, "closing"),
        ("ae", "meeting", {"contact": None, "inbound": None, "deal_stage": None}, "closing"),
        ("ae", "visit", CONTACTED, "closing"),
        # An AE call that is not a first contact has no rule: role default (closing).
        ("ae", "call", CONTACTED, "closing"),
        # A voice note matches no channel list.
        ("ae", "voice_note", NEW, "closing"),
        ("sdr", "voice_note", NEW, "discovery"),
        # General follows the channel; an sdr/ae rule does not claim a general rep.
        ("general", "call", INBOUND, "discovery"),
        (None, "meeting", NEW, "closing"),
    ],
)
def test_catalog_defaults_route_by_role_channel_and_context(role, kind, context, expected):
    assert motion_for(role, kind, context, _catalog_rules()) == expected


def test_only_a_published_rule_routes():
    unpublished_inbound = _catalog_rules(published=("discovery", "closing", "ae_discovery"))
    assert motion_for("sdr", "call", INBOUND, unpublished_inbound) == "discovery"
    nothing_published = _catalog_rules(published=())
    assert motion_for("ae", "meeting", NEW, nothing_published) == "closing"
    assert route("ae", "meeting", NEW, nothing_published) == ("closing", "role_default")


def test_route_says_why():
    rules = _catalog_rules()
    assert route("ae", "meeting", NEW, rules) == ("ae_discovery", "rule")
    assert route("ae", "meeting", CONTACTED, rules) == ("closing", "rule")
    assert route("general", "voice_note", None, rules) == (None, None)


def test_negotiation_only_matches_when_stages_are_configured():
    published = ("discovery", "inbound", "ae_discovery", "closing", "negotiation")
    at_proposal = {"contact": "contacted", "inbound": None, "deal_stage": "proposal"}
    # No stages picked: negotiation never matches, whatever the deal is doing.
    assert motion_for("ae", "meeting", at_proposal, _catalog_rules(published)) == "closing"
    configured = _catalog_rules(published, stages={"negotiation": ["proposal", "contract"]})
    assert motion_for("ae", "meeting", at_proposal, configured) == "negotiation"
    # 3 conditions (role, channels, stages) beat closing's 2.
    assert motion_for("ae", "visit", {"contact": "contacted", "deal_stage": "contract"}, configured) == "negotiation"
    # Another stage, or an unknown one: closing.
    assert motion_for("ae", "meeting", {"contact": "contacted", "deal_stage": "qualified"}, configured) == "closing"
    assert motion_for("ae", "meeting", {"contact": "contacted", "deal_stage": None}, configured) == "closing"
    # negotiation also covers calls (its channels), closing does not.
    assert motion_for("ae", "call", {"contact": "contacted", "deal_stage": "proposal"}, configured) == "negotiation"


def test_two_ae_playbooks_with_stages_pick_the_one_whose_stage_the_deal_is_in():
    published = ("ae_discovery", "closing", "negotiation")
    rules = _catalog_rules(
        published,
        stages={"ae_discovery": ["appointment"], "negotiation": ["proposal", "contract"]},
    )
    # ae_discovery keeps contact "new" (default) AND now needs the stage: 4 conditions.
    in_appointment_new = {"contact": "new", "deal_stage": "appointment"}
    assert motion_for("ae", "meeting", in_appointment_new, rules) == "ae_discovery"
    in_appointment_contacted = {"contact": "contacted", "deal_stage": "appointment"}
    assert motion_for("ae", "meeting", in_appointment_contacted, rules) == "closing"
    assert motion_for("ae", "meeting", {"contact": "contacted", "deal_stage": "proposal"}, rules) == "negotiation"
    assert motion_for("ae", "meeting", {"contact": "contacted", "deal_stage": "contract"}, rules) == "negotiation"
    # The stage is the only thing the CRM told us and it matches no rule: role default.
    assert motion_for("ae", "meeting", {"contact": "contacted", "deal_stage": "won"}, rules) == "closing"


def test_ae_discovery_can_be_pinned_to_stages_instead_of_the_first_meeting():
    rules = _catalog_rules(("ae_discovery", "closing"))
    rules[2]["applies_to"] = {"role": "ae", "channels": ["meeting"], "contact": "any", "deal_stages": ["qualified"]}
    assert motion_for("ae", "meeting", {"contact": "contacted", "deal_stage": "qualified"}, rules) == "ae_discovery"
    assert motion_for("ae", "meeting", NEW, rules) == "closing"


def test_no_crm_means_no_context_and_the_role_default():
    published = ("discovery", "inbound", "ae_discovery", "closing", "negotiation")
    rules = _catalog_rules(published, stages={"negotiation": ["proposal"]})
    unknown = {"contact": None, "inbound": None, "deal_stage": None}
    assert motion_for("ae", "meeting", unknown, rules) == "closing"
    assert motion_for("sdr", "call", unknown, rules) == "discovery"
    assert motion_for("ae", "meeting", None, rules) == "closing"


def test_tie_goes_to_catalog_order_then_key():
    custom_a = {"key": "zeta", "applies_to": {"role": "ae", "channels": ["meeting"], "contact": "any", "deal_stages": []}, "published": True}
    custom_b = {"key": "alpha", "applies_to": {"role": "ae", "channels": ["meeting"], "contact": "any", "deal_stages": []}, "published": True}
    # closing has the same two conditions: the catalog type first, then customs by key.
    assert motion_for("ae", "meeting", CONTACTED, [custom_a, custom_b] + _catalog_rules()) == "closing"
    assert motion_for("ae", "meeting", CONTACTED, [custom_a, custom_b]) == "alpha"
    # The order of the list does not matter.
    assert motion_for("ae", "meeting", CONTACTED, [custom_b, custom_a]) == "alpha"


def test_a_custom_type_with_more_conditions_beats_the_defaults():
    renewal = {
        "key": "renewal",
        "applies_to": {"role": "ae", "channels": ["call"], "contact": "contacted", "deal_stages": ["renewal_due"]},
        "published": True,
    }
    rules = _catalog_rules() + [renewal]
    assert motion_for("ae", "call", {"contact": "contacted", "deal_stage": "renewal_due"}, rules) == "renewal"
    # Its stage is unknown, so the custom type does not match.
    assert motion_for("ae", "call", {"contact": "contacted", "deal_stage": None}, rules) == "closing"


def test_an_any_role_custom_type_matches_general_reps():
    custom = {"key": "callback", "applies_to": {"role": "any", "channels": ["call"], "contact": "contacted", "deal_stages": []}, "published": True}
    assert motion_for("general", "call", CONTACTED, [custom]) == "callback"
    assert motion_for(None, "call", CONTACTED, [custom]) == "callback"
    assert motion_for("sdr", "call", CONTACTED, [custom]) == "callback"
    assert motion_for("sdr", "call", NEW, [custom]) == "discovery"


def test_a_rule_that_is_not_a_dict_is_skipped():
    rules = [{"key": "broken", "applies_to": None, "published": True}, {"key": "", "applies_to": {}, "published": True}]
    assert motion_for("sdr", "call", NEW, rules) == "discovery"


def test_rules_from_uses_catalog_defaults_and_the_stored_rule():
    motions = {"discovery": "published", "closing": "draft", "qualification": "published", "renewal": "published"}
    stored = {
        "renewal": {"label": "Renovación", "applies_to": {"role": "ae", "channels": ["call"], "contact": "contacted", "deal_stages": []}},
        "closing": {"label": None, "applies_to": {"role": "nonsense"}},  # invalid: falls back to the default
    }
    rules = {rule["key"]: rule for rule in rules_from(motions, stored)}
    assert rules["discovery"]["published"] is True
    assert rules["closing"]["published"] is False
    assert rules["closing"]["applies_to"] == default_applies_to("closing")
    assert rules["renewal"]["applies_to"]["contact"] == "contacted"
    assert "qualification" not in rules  # no rule, no catalog default: never routed to
    assert [rule["key"] for rule in rules_from(motions, stored)][:5] == [
        "discovery", "inbound", "ae_discovery", "closing", "negotiation",
    ]
