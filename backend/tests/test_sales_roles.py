"""Tests for T1: sales_role, SDR->AE routing and visibility per member (D1-D3)."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-sales-roles")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-sales-roles")

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services.company import CompanyService, Membership


def _actor(role: str = "owner") -> Membership:
    return Membership(
        id="actor-member",
        company_id="company-1",
        user_id="actor-user",
        role=role,
        status="active",
    )


def test_update_member_profile_requires_manage_role():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    with pytest.raises(HTTPException) as exc:
        svc.update_member_profile(
            company_id="company-1",
            actor=_actor("member"),
            member_id="m1",
            sales_role="sdr",
        )
    assert exc.value.status_code == 403


def test_update_member_profile_rejects_invalid_sales_role():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc._get_member_row = MagicMock(return_value={"id": "m1", "user_id": "u1", "role": "member"})
    with pytest.raises(HTTPException) as exc:
        svc.update_member_profile(
            company_id="company-1",
            actor=_actor(),
            member_id="m1",
            sales_role="closer",
        )
    assert exc.value.status_code == 400


def test_update_member_profile_rejects_invalid_visibility():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc._get_member_row = MagicMock(return_value={"id": "m1", "user_id": "u1", "role": "member"})
    with pytest.raises(HTTPException) as exc:
        svc.update_member_profile(
            company_id="company-1",
            actor=_actor(),
            member_id="m1",
            visibility="everyone",
        )
    assert exc.value.status_code == 400


def test_update_member_profile_rejects_self_handoff():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc._get_member_row = MagicMock(return_value={"id": "m1", "user_id": "sdr-1", "role": "member"})
    with pytest.raises(HTTPException) as exc:
        svc.update_member_profile(
            company_id="company-1",
            actor=_actor(),
            member_id="m1",
            handoff_ae_user_id="sdr-1",
        )
    assert exc.value.status_code == 400
    assert "themselves" in exc.value.detail


def test_update_member_profile_rejects_ae_not_ae_or_general():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc._get_member_row = MagicMock(return_value={"id": "m1", "user_id": "sdr-1", "role": "member"})
    svc._get_member_row_by_user_id = MagicMock(
        return_value={"id": "m2", "user_id": "sdr-2", "sales_role": "sdr", "status": "active"}
    )
    with pytest.raises(HTTPException) as exc:
        svc.update_member_profile(
            company_id="company-1",
            actor=_actor(),
            member_id="m1",
            handoff_ae_user_id="sdr-2",
        )
    assert exc.value.status_code == 400
    assert "AE" in exc.value.detail


def test_update_member_profile_accepts_ae_with_null_sales_role_as_general():
    """D1: a null sales_role behaves as 'general' and is a valid handoff target."""
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc._get_member_row = MagicMock(return_value={"id": "m1", "user_id": "sdr-1", "role": "member"})
    svc._get_member_row_by_user_id = MagicMock(
        return_value={"id": "m2", "user_id": "ae-1", "sales_role": None, "status": "active"}
    )
    update_mock = supabase.table.return_value.update.return_value.eq.return_value.eq.return_value.execute
    update_mock.return_value = MagicMock(data=[{"id": "m1", "handoff_ae_user_id": "ae-1"}])

    result = svc.update_member_profile(
        company_id="company-1",
        actor=_actor(),
        member_id="m1",
        handoff_ae_user_id="ae-1",
    )
    assert result["handoff_ae_user_id"] == "ae-1"


def test_update_member_profile_rejects_inactive_ae():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc._get_member_row = MagicMock(return_value={"id": "m1", "user_id": "sdr-1", "role": "member"})
    svc._get_member_row_by_user_id = MagicMock(
        return_value={"id": "m2", "user_id": "ae-1", "sales_role": "ae", "status": "disabled"}
    )
    with pytest.raises(HTTPException) as exc:
        svc.update_member_profile(
            company_id="company-1",
            actor=_actor(),
            member_id="m1",
            handoff_ae_user_id="ae-1",
        )
    assert exc.value.status_code == 400
    assert "active" in exc.value.detail


def test_update_member_profile_accepts_valid_handoff_and_role():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc._get_member_row = MagicMock(return_value={"id": "m1", "user_id": "sdr-1", "role": "member"})
    svc._get_member_row_by_user_id = MagicMock(
        return_value={"id": "m2", "user_id": "ae-1", "sales_role": "ae"}
    )
    update_mock = supabase.table.return_value.update.return_value.eq.return_value.eq.return_value.execute
    update_mock.return_value = MagicMock(
        data=[{"id": "m1", "sales_role": "sdr", "handoff_ae_user_id": "ae-1", "visibility": "own"}]
    )

    result = svc.update_member_profile(
        company_id="company-1",
        actor=_actor(),
        member_id="m1",
        sales_role="sdr",
        handoff_ae_user_id="ae-1",
        visibility="team",
    )

    assert result["handoff_ae_user_id"] == "ae-1"
    called_payload = supabase.table.return_value.update.call_args[0][0]
    assert called_payload["sales_role"] == "sdr"
    assert called_payload["handoff_ae_user_id"] == "ae-1"
    assert called_payload["visibility"] == "team"


def test_update_member_profile_can_clear_handoff():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc._get_member_row = MagicMock(return_value={"id": "m1", "user_id": "sdr-1", "role": "member"})
    update_mock = supabase.table.return_value.update.return_value.eq.return_value.eq.return_value.execute
    update_mock.return_value = MagicMock(data=[{"id": "m1", "handoff_ae_user_id": None}])

    svc.update_member_profile(
        company_id="company-1",
        actor=_actor(),
        member_id="m1",
        handoff_ae_user_id=None,
    )
    called_payload = supabase.table.return_value.update.call_args[0][0]
    assert called_payload["handoff_ae_user_id"] is None


def test_update_member_profile_noop_when_nothing_provided():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    target = {"id": "m1", "user_id": "sdr-1", "role": "member"}
    svc._get_member_row = MagicMock(return_value=target)

    result = svc.update_member_profile(
        company_id="company-1",
        actor=_actor(),
        member_id="m1",
    )
    assert result == target
    supabase.table.return_value.update.assert_not_called()


def test_create_invite_rejects_invalid_sales_role():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc.ensure_seat_available = MagicMock()
    svc._email_exists_in_auth = MagicMock(return_value=None)
    import asyncio

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            svc.create_invite(
                company_id="company-1",
                email="new@acme.com",
                role="member",
                sales_role="closer",
            )
        )
    assert exc.value.status_code == 400


def test_accept_invite_copies_sales_role_to_membership():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc.get_invite_by_token = MagicMock(
        return_value={
            "id": "invite-1",
            "company_id": "company-1",
            "email": "sdr@acme.com",
            "role": "member",
            "sales_role": "sdr",
        }
    )
    svc._email_exists_in_auth = MagicMock(return_value=None)

    auth_client = MagicMock()
    auth_client.auth.sign_up.return_value = MagicMock(user=MagicMock(id="new-user-1"))

    svc.accept_invite(
        raw_token="raw-token",
        password="a-long-password",
        full_name="New SDR",
        auth_client=auth_client,
    )

    insert_calls = supabase.table.return_value.insert.call_args_list
    member_insert = next(
        call.args[0] for call in insert_calls if call.args[0].get("role") == "member"
    )
    assert member_insert["sales_role"] == "sdr"


def test_accept_invite_omits_sales_role_when_invite_has_none():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc.get_invite_by_token = MagicMock(
        return_value={
            "id": "invite-1",
            "company_id": "company-1",
            "email": "member@acme.com",
            "role": "member",
            "sales_role": None,
        }
    )
    svc._email_exists_in_auth = MagicMock(return_value=None)

    auth_client = MagicMock()
    auth_client.auth.sign_up.return_value = MagicMock(user=MagicMock(id="new-user-1"))

    svc.accept_invite(
        raw_token="raw-token",
        password="a-long-password",
        full_name="New member",
        auth_client=auth_client,
    )

    insert_calls = supabase.table.return_value.insert.call_args_list
    member_insert = next(
        call.args[0] for call in insert_calls if call.args[0].get("role") == "member"
    )
    assert "sales_role" not in member_insert


def test_create_invite_omits_sales_role_column_when_not_provided():
    import asyncio

    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc.ensure_seat_available = MagicMock()
    svc._email_exists_in_auth = MagicMock(return_value=None)
    svc.get_company = MagicMock(return_value={"name": "Acme"})
    insert_mock = supabase.table.return_value.insert.return_value.execute
    insert_mock.return_value = MagicMock(
        data=[{"id": "inv-1", "email": "new@acme.com", "role": "member", "expires_at": "2026-01-01T00:00:00Z"}]
    )

    asyncio.run(
        svc.create_invite(
            company_id="company-1",
            email="new@acme.com",
            role="member",
            send_email=False,
        )
    )
    called_payload = supabase.table.return_value.insert.call_args[0][0]
    assert "sales_role" not in called_payload


def test_get_member_row_by_user_id_is_400_not_500_for_non_member():
    """single() raises (500) on zero rows; limit(1) lets a bad handoff_ae_user_id be a 400."""
    supabase = MagicMock()
    svc = CompanyService(supabase)
    chain = supabase.table.return_value.select.return_value.eq.return_value.eq.return_value
    chain.limit.return_value.execute.return_value = MagicMock(data=[])

    with pytest.raises(HTTPException) as exc:
        svc._get_member_row_by_user_id("company-1", "nobody")
    assert exc.value.status_code == 400


def test_get_membership_falls_back_before_migration_054():
    """A 42703 undefined-column error on sales_role/handoff_ae_user_id/visibility retries
    with the pre-migration column list instead of failing get_membership outright."""
    from postgrest.exceptions import APIError

    supabase = MagicMock()
    err = APIError(
        {
            "message": 'column company_members.sales_role does not exist',
            "code": "42703",
            "details": None,
            "hint": None,
        }
    )
    fallback_result = MagicMock(
        data=[{"id": "m1", "company_id": "c1", "user_id": "u1", "role": "member", "status": "active"}]
    )
    chain = supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute
    chain.side_effect = [err, fallback_result]

    svc = CompanyService(supabase)
    membership = svc.get_membership("u1")
    assert membership is not None
    assert membership.role == "member"
    assert membership.sales_role is None
    assert membership.handoff_ae_user_id is None
    assert membership.visibility == "own"


def test_get_membership_reraises_other_errors():
    supabase = MagicMock()
    chain = supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute
    chain.side_effect = RuntimeError("boom")

    svc = CompanyService(supabase)
    with pytest.raises(RuntimeError):
        svc.get_membership("u1")


def test_approve_denies_a_team_visibility_member_reading_a_teammates_memo():
    """BLOCKING: approve is a write path. visibility=team is read-only (D3) and must
    not let a teammate approve someone else's memo."""
    import asyncio

    from app.services import memo_approval

    class _Result:
        def __init__(self, data):
            self.data = data

    class _Query:
        def __init__(self, tables, name):
            self._tables = tables
            self._name = name
            self._filters: list[tuple[str, object]] = []

        def select(self, *_a, **_k):
            return self

        def eq(self, column, value):
            self._filters.append((column, value))
            return self

        def order(self, *_a, **_k):
            return self

        def limit(self, _n):
            return self

        def in_(self, column, values):
            values = set(values)
            self._filters.append((column, values))
            return self

        def single(self):
            return self

        def execute(self):
            rows = list(self._tables.get(self._name, []))
            for column, value in self._filters:
                if isinstance(value, set):
                    rows = [r for r in rows if r.get(column) in value]
                else:
                    rows = [r for r in rows if r.get(column) == value]
            return _Result(rows)

    class _DB:
        def __init__(self, **tables):
            self.tables = tables

        def table(self, name):
            return _Query(self.tables, name)

    memo_id = "memo-1"
    db = _DB(
        memos=[
            {
                "id": memo_id,
                "user_id": "owner-1",
                "company_id": "co-1",
                "status": "pending_review",
                "extraction": {},
            }
        ],
        company_members=[
            {
                "id": "m-viewer",
                "user_id": "viewer-1",
                "company_id": "co-1",
                "role": "member",
                "status": "active",
                "sales_role": None,
                "handoff_ae_user_id": None,
                "visibility": "team",
            },
            {
                "id": "m-owner",
                "user_id": "owner-1",
                "company_id": "co-1",
                "role": "member",
                "status": "active",
                "sales_role": None,
                "handoff_ae_user_id": None,
                "visibility": "own",
            },
        ],
        user_profiles=[],
    )

    with pytest.raises(ValueError, match="Memo not found"):
        asyncio.run(memo_approval.approve_memo_core(db, memo_id, "viewer-1", None))
