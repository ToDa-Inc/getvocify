"""Where a call is saved (crm_configurations.call_targets): the rule, and what the approval sends the CRM."""
from app.services.call_targets import pick, targets_for
from tests.test_after_call_http import _config, _Env, fresh_flags  # noqa: F401 (autouse fixture)


class _Config:
    def __init__(self, call_targets):
        self.call_targets = call_targets


def test_all_three_before_the_setting_exists():
    assert targets_for(None) == {"deal", "company", "contact"}
    assert targets_for(_Config(None)) == {"deal", "company", "contact"}


def test_the_reps_choice_wins_over_the_company_setting():
    assert targets_for(_Config(["contact"]), ["deal"]) == {"deal"}
    assert targets_for(_Config(["contact"]), []) == {"contact"}


def test_the_call_goes_only_on_the_chosen_records_it_has():
    assert pick({"deal"}, deal_id="d", contact_id="c", company_id="o") == ("d", None, None)
    assert pick({"contact", "company"}, deal_id="d", contact_id="c", company_id=None) == (None, "c", None)


def test_a_call_with_none_of_the_chosen_records_is_never_lost():
    assert pick({"deal"}, deal_id=None, contact_id="c", company_id="o") == (None, "c", "o")


def test_without_deal_the_approval_neither_updates_nor_creates_one(monkeypatch):
    env = _Env(monkeypatch, provider="pipedrive", config=_config(call_targets=["contact", "company"]))
    env.approve(deal_id="d-9")
    [call] = env.provider.calls
    assert call["skip_deal"] is True and call["deal_id"] is None and call["is_new_deal"] is False
    assert call["link_to"] == {"contact", "company"}


def test_the_review_can_save_one_call_elsewhere(monkeypatch):
    env = _Env(monkeypatch, provider="pipedrive", config=_config(call_targets=["contact"]))
    env.approve(deal_id="d-9", call_targets=["deal"])
    [call] = env.provider.calls
    assert call["deal_id"] == "d-9" and call["skip_deal"] is False
    assert call["link_to"] == {"deal"}


def test_salesforce_keeps_its_opportunity(monkeypatch):
    env = _Env(monkeypatch, provider="salesforce", config=_config(call_targets=["contact"]))
    env.approve(deal_id="d-9")
    [call] = env.provider.calls
    assert call["skip_deal"] is False and "link_to" not in call


def test_the_island_saves_on_the_deal_it_showed_and_where_the_rep_left_it(monkeypatch):
    from tests.test_after_call_http import MEMO

    env = _Env(monkeypatch, provider="pipedrive", config=_config(call_targets=["deal", "company", "contact"]))
    env.store.tables["memos"][0]["pipeline_meta"] = {"crm_company_id": "77"}
    response = env.client().post(
        f"/api/v1/memos/{MEMO}/approve-contact", json={"deal_id": "d-5", "call_targets": ["deal", "contact"]}
    )
    assert response.status_code == 200, response.text
    [call] = env.provider.calls
    assert call["deal_id"] == "d-5" and call["skip_deal"] is False
    assert call["company_id"] == "77"
    assert call["link_to"] == {"deal", "contact"}


def test_a_record_the_call_isnt_saved_on_is_left_alone(monkeypatch):
    env = _Env(
        monkeypatch,
        provider="pipedrive",
        config=_config(call_targets=["deal", "contact"], auto_create_companies=True, allowed_company_fields=["name", "industry"]),
    )
    env.store.tables["memos"][0]["extraction"]["raw_extraction"] = {
        "company_properties": {"industry": "Logistics"},
        "contact_properties": {"jobtitle": "COO"},
    }
    env.approve(deal_id="d-9")
    [call] = env.provider.calls
    assert call["auto_create_companies"] is False and call["allowed_company_fields"] == []
    raw = call["extraction"].raw_extraction or {}
    assert "company_properties" not in raw and raw["contact_properties"] == {"jobtitle": "COO"}
