from app.services.activity_scope import (
    UnknownCompanyAuthor,
    annotate_recording_author,
    author_display_name,
    authors_by_user_id,
    can_view_company_activity,
    invert_hubspot_owners,
    memo_readable_by,
    resolve_list_user_ids,
    visible_recordings_for_viewer,
)
import pytest


def test_can_view_company_activity_is_owner_or_admin():
    assert can_view_company_activity("owner") is True
    assert can_view_company_activity("admin") is True
    assert can_view_company_activity("member") is False
    assert can_view_company_activity(None) is False


def test_author_display_name_prefers_full_name():
    assert author_display_name("Dana Vale", "dana@acme.com") == "Dana Vale"
    assert author_display_name("  ", "dana@acme.com") == "dana"
    assert author_display_name(None, None) == "Teammate"


def test_authors_by_user_id_includes_inactive_for_labels():
    authors = authors_by_user_id(
        [
            {"user_id": "u1", "full_name": "Ada", "email": "ada@acme.com", "status": "active"},
            {"user_id": "u2", "full_name": None, "email": "bob@acme.com", "status": "removed"},
        ]
    )
    assert authors["u1"]["name"] == "Ada"
    assert authors["u2"]["name"] == "bob"


def test_member_list_is_always_self():
    assert resolve_list_user_ids(
        viewer_id="u1",
        viewer_role="member",
        member_ids=["u1", "u2"],
        scope="company",
    ) == ["u1"]


def test_owner_company_scope_returns_team():
    ids = resolve_list_user_ids(
        viewer_id="u1",
        viewer_role="owner",
        member_ids=["u1", "u2"],
        scope="company",
    )
    assert set(ids) == {"u1", "u2"}


def test_owner_can_filter_to_one_teammate():
    assert resolve_list_user_ids(
        viewer_id="u1",
        viewer_role="admin",
        member_ids=["u1", "u2"],
        scope="company",
        author_user_id="u2",
    ) == ["u2"]


def test_unknown_company_author_raises():
    with pytest.raises(UnknownCompanyAuthor):
        resolve_list_user_ids(
            viewer_id="u1",
            viewer_role="owner",
            member_ids=["u1", "u2"],
            scope="company",
            author_user_id="outsider",
        )


def test_memo_readable_by_owner_same_company():
    assert memo_readable_by(
        viewer_id="owner",
        owner_user_id="rep",
        viewer_role="owner",
        same_company=True,
    )
    assert not memo_readable_by(
        viewer_id="owner",
        owner_user_id="rep",
        viewer_role="owner",
        same_company=False,
    )
    assert not memo_readable_by(
        viewer_id="rep-a",
        owner_user_id="rep-b",
        viewer_role="member",
        same_company=True,
    )


def test_invert_hubspot_owners_ignores_legacy_key():
    assert invert_hubspot_owners({"hubspot_owner_id": "999"}) == {}
    assert invert_hubspot_owners({"hubspot_owners": {"u1": "111", "u2": "222"}}) == {
        "111": "u1",
        "222": "u2",
    }


def test_annotate_and_filter_recordings():
    authors = {"u1": {"user_id": "u1", "name": "Ada", "email": "ada@acme.com"}}
    rec = annotate_recording_author(
        {"call_id": "c1", "hubspot_owner_id": "111"},
        authors,
        {"111": "u1"},
    )
    assert rec["author_user_id"] == "u1"
    assert rec["author_name"] == "Ada"
    other = annotate_recording_author(
        {"call_id": "c2", "hubspot_owner_id": "999"},
        authors,
        {"111": "u1"},
    )
    assert other["author_user_id"] is None
    visible = visible_recordings_for_viewer(
        [rec, other],
        viewer_id="u1",
        can_view_company=False,
    )
    assert [r["call_id"] for r in visible] == ["c1"]
    assert len(visible_recordings_for_viewer(
        [rec, other],
        viewer_id="u1",
        can_view_company=True,
    )) == 2
