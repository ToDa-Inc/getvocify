from app.services.hubspot.sync import (
    owner_id_from_connection_metadata,
    stamp_owner,
    with_cached_owner_id,
)


def test_legacy_global_owner_id_is_ignored():
    meta = {"hubspot_owner_id": "999"}
    assert owner_id_from_connection_metadata(meta, "user-1") is None


def test_per_user_owner_cache_hit():
    meta = {"hubspot_owners": {"user-1": "111", "user-2": "222"}}
    assert owner_id_from_connection_metadata(meta, "user-1") == "111"
    assert owner_id_from_connection_metadata(meta, "user-2") == "222"


def test_missing_user_returns_none():
    meta = {"hubspot_owners": {"user-1": "111"}}
    assert owner_id_from_connection_metadata(meta, "user-3") is None


def test_with_cached_owner_id_does_not_write_legacy_key():
    meta = with_cached_owner_id({"hubspot_owner_id": "999"}, "user-1", "111")
    assert meta["hubspot_owners"]["user-1"] == "111"
    assert meta["hubspot_owner_id"] == "999"
    assert owner_id_from_connection_metadata(meta, "user-1") == "111"
    assert owner_id_from_connection_metadata(meta, "user-2") is None


def test_stamp_owner_writes_assignment_on_update_props():
    assert stamp_owner({"phone": "1"}, "111") == {
        "phone": "1",
        "hubspot_owner_id": "111",
    }
    assert stamp_owner({}, None) == {}
    assert stamp_owner(None, "111")["hubspot_owner_id"] == "111"
