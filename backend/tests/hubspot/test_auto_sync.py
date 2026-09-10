from app.models.crm_config import CRMConfigurationRequest
from app.services.hubspot.auto_sync import (
    approval_payload_for_auto_sync,
    connection_matches_portal,
    recording_ready_jobs,
    resolve_auto_sync_user_id,
    should_auto_approve_hubspot_call,
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


def test_auto_approve_requires_hubspot_call_toggle_and_locked_record():
    assert (
        should_auto_approve_hubspot_call(
            source="hubspot_call",
            auto_sync_enabled=True,
            contact_id="c1",
            deal_id=None,
        )
        is True
    )
    assert (
        should_auto_approve_hubspot_call(
            source="hubspot_call",
            auto_sync_enabled=True,
            contact_id=None,
            deal_id="d1",
        )
        is True
    )
    assert (
        should_auto_approve_hubspot_call(
            source="hubspot_call",
            auto_sync_enabled=True,
            contact_id="",
            deal_id="  ",
        )
        is False
    )
    assert (
        should_auto_approve_hubspot_call(
            source="hubspot_call",
            auto_sync_enabled=False,
            contact_id="c1",
            deal_id="d1",
        )
        is False
    )
    assert (
        should_auto_approve_hubspot_call(
            source="vocify_call",
            auto_sync_enabled=True,
            contact_id="c1",
            deal_id="d1",
        )
        is False
    )


def test_auto_sync_payload_never_creates_a_deal_or_sets_lead_status():
    with_deal = approval_payload_for_auto_sync(contact_id="c1", deal_id="d1")
    assert with_deal.deal_id == "d1"
    assert with_deal.contact_id == "c1"
    assert with_deal.is_new_deal is False
    assert with_deal.skip_deal is False
    assert with_deal.call_outcome is None
    assert with_deal.create_note is True

    contact_only = approval_payload_for_auto_sync(contact_id="c1", deal_id=None)
    assert contact_only.deal_id is None
    assert contact_only.skip_deal is True
    assert contact_only.is_new_deal is False
    assert contact_only.call_outcome is None


def test_crm_config_defaults_auto_sync_off():
    req = CRMConfigurationRequest(
        default_pipeline_id="p",
        default_pipeline_name="Sales",
        default_stage_id="s",
        default_stage_name="New",
    )
    assert req.auto_sync_hubspot_calls is False
