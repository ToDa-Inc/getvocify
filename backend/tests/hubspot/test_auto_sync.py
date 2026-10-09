from app.models.crm_config import CRMConfigurationRequest
from app.services.hubspot.auto_sync import (
    approval_payload_for_auto_sync,
    connection_matches_portal,
    recording_ready_jobs,
    resolve_auto_sync_user_id,
    should_auto_approve,
    should_start_auto_sync,
)


def test_recording_ready_jobs_only_keep_calls_with_a_recording_url():
    jobs = recording_ready_jobs(
        [
            {
                "subscriptionType": "engagement.propertyChange",
                "portalId": 111,
                "objectId": 101,
                "propertyName": "hs_call_title",
                "propertyValue": "Intro",
            },
            {
                "subscriptionType": "engagement.propertyChange",
                "portalId": 111,
                "objectId": 202,
                "propertyName": "hs_call_recording_url",
                "propertyValue": "",
            },
            {
                "subscriptionType": "engagement.propertyChange",
                "portalId": 111,
                "objectId": 303,
                "propertyName": "hs_call_recording_url",
                "propertyValue": "https://api.hubspot.com/recording.mp3",
            },
            {
                "subscriptionType": "engagement.creation",
                "portalId": 111,
                "objectId": 404,
            },
        ]
    )
    assert jobs == [("111", "303")]


def test_recording_ready_jobs_accept_object_property_change():
    jobs = recording_ready_jobs(
        [
            {
                "subscriptionType": "object.propertyChange",
                "portalId": "222",
                "objectId": "909",
                "propertyName": "hs_call_recording_url",
                "propertyValue": "https://example.com/a.mp3",
            }
        ]
    )
    assert jobs == [("222", "909")]


def test_connection_matches_portal_compares_stored_metadata():
    assert connection_matches_portal({"portal_id": "555"}, "555") is True
    assert connection_matches_portal({"portal_id": 555}, "555") is True
    assert connection_matches_portal({"portal_id": "555"}, "999") is False
    assert connection_matches_portal({}, "555") is False
    assert connection_matches_portal(None, "555") is False


def test_should_start_auto_sync_is_off_by_default():
    assert should_start_auto_sync(None) is False
    assert should_start_auto_sync(False) is False
    assert should_start_auto_sync(True) is True


def test_resolve_auto_sync_user_prefers_call_owner_mapping():
    assert (
        resolve_auto_sync_user_id(
            "ow-1",
            {"ow-1": "user-alvaro"},
            "user-dani",
        )
        == "user-alvaro"
    )


def test_resolve_auto_sync_user_falls_back_to_connector():
    assert resolve_auto_sync_user_id("ow-missing", {"ow-1": "user-alvaro"}, "user-dani") == "user-dani"
    assert resolve_auto_sync_user_id(None, {}, "user-dani") == "user-dani"
    assert resolve_auto_sync_user_id("ow-1", {}, None) is None


def test_resolve_auto_sync_user_does_not_guess_on_a_team():
    assert (
        resolve_auto_sync_user_id(
            "ow-missing",
            {"ow-1": "user-alvaro"},
            "user-dani",
            team_size=3,
        )
        is None
    )
    assert (
        resolve_auto_sync_user_id(
            None,
            {},
            "user-dani",
            team_size=3,
        )
        == "user-dani"
    )


def test_auto_approve_requires_toggle_and_locked_record():
    assert should_auto_approve(auto_sync_enabled=True, contact_id="c1", deal_id=None) is True
    assert should_auto_approve(auto_sync_enabled=True, contact_id=None, deal_id="d1") is True
    assert should_auto_approve(auto_sync_enabled=True, contact_id="", deal_id="  ") is False
    assert should_auto_approve(auto_sync_enabled=False, contact_id="c1", deal_id="d1") is False


def test_auto_approve_covers_dialer_and_voice_memo_when_locked():
    assert should_auto_approve(auto_sync_enabled=True, contact_id="c1", deal_id="d1") is True
    assert should_auto_approve(auto_sync_enabled=True, contact_id="c1", deal_id=None) is True


def test_auto_approve_skips_screened_out_calls():
    assert (
        should_auto_approve(
            auto_sync_enabled=True,
            contact_id="c1",
            deal_id="d1",
            screening_outcome="voicemail",
        )
        is False
    )
    assert (
        should_auto_approve(
            auto_sync_enabled=True,
            contact_id="c1",
            deal_id="d1",
            screening_outcome="connected",
        )
        is True
    )


def test_auto_sync_payload_never_creates_a_deal_or_sets_lead_status():
    with_deal = approval_payload_for_auto_sync(contact_id="c1", deal_id="d1")
    assert with_deal.deal_id == "d1"
    assert with_deal.contact_id == "c1"
    assert with_deal.is_new_deal is False
    assert with_deal.skip_deal is False
    assert with_deal.call_outcome is None
    assert with_deal.create_note is True
    assert with_deal.create_company is False

    contact_only = approval_payload_for_auto_sync(contact_id="c1", deal_id=None)
    assert contact_only.deal_id is None
    assert contact_only.skip_deal is True
    assert contact_only.is_new_deal is False
    assert contact_only.call_outcome is None
    assert contact_only.create_company is False


def test_crm_config_defaults_auto_sync_off():
    req = CRMConfigurationRequest(
        default_pipeline_id="p",
        default_pipeline_name="Sales",
        default_stage_id="s",
        default_stage_name="New",
    )
    assert req.auto_sync_hubspot_calls is False


# --- a rep who records with the island never has their dialer's recordings processed ------------

import asyncio  # noqa: E402

import pytest  # noqa: E402

from app.services.hubspot import auto_sync  # noqa: E402

RECORDING_EVENT = {"subscriptionType": "engagement.propertyChange", "propertyName": "hs_call_recording_url",
                   "propertyValue": "https://api.hubspot.com/recording/1", "portalId": 123, "objectId": 456}


class _Profiles:
    def __init__(self, value):
        self.value = value

    def table(self, _name):
        rows = [] if self.value is None else [{"process_crm_call_recordings": self.value}]
        chain = type("Chain", (), {})()
        chain.select = chain.eq = chain.limit = lambda *_a, **_k: chain
        chain.execute = lambda: type("R", (), {"data": rows})()
        return chain


@pytest.fixture
def started(monkeypatch):
    calls = []

    async def fresh(_db, conn):
        return conn

    async def user(*_a, **_k):
        return "user-1"

    async def enqueue(_db, user_id, call_id, _token):
        calls.append((user_id, call_id))
        return {"memo_id": "memo-1", "status": "transcribing"}

    monkeypatch.setattr(auto_sync, "find_hubspot_connection_for_portal", lambda *_a: {"id": "conn-1", "access_token": "t"})
    monkeypatch.setattr(auto_sync, "auto_sync_enabled_for_connection", lambda *_a: True)
    monkeypatch.setattr("app.services.hubspot.token_refresh.ensure_hubspot_connection_tokens_fresh", fresh)
    monkeypatch.setattr(auto_sync, "resolve_user_for_hubspot_call", user)
    monkeypatch.setattr("app.services.hubspot.call_processor.enqueue_hubspot_call_process", enqueue)
    return calls


@pytest.mark.parametrize("value, processed", [(True, True), (None, False), (False, False)])
def test_the_reps_switch_decides_after_the_company_switch(started, value, processed):
    done, skipped = asyncio.run(auto_sync.handle_hubspot_recording_events(_Profiles(value), [RECORDING_EVENT]))
    assert (done, skipped) == ((1, 0) if processed else (0, 1))
    assert bool(started) is processed


def test_a_missing_column_means_process_as_before():
    class Broken:
        def table(self, _name):
            raise RuntimeError('column "process_crm_call_recordings" does not exist')

    assert auto_sync.read_crm_call_recordings_preference(Broken(), "user-1") is True
