"""F17 sales_role API: invites, accept, list, session, PATCH (E1–E12)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api import company as company_api
from app.deps import get_supabase, get_user_id
from app.services.company import CompanyService, Membership


def _membership(
    *,
    role: str = "owner",
    user_id: str = "u-owner",
    company_id: str = "co-1",
    member_id: str = "m-1",
    status: str = "active",
    sales_role: str = "general",
) -> Membership:
    return Membership(
        id=member_id,
        company_id=company_id,
        user_id=user_id,
        role=role,
        status=status,
        sales_role=sales_role,
    )


def _capture_insert(supabase: MagicMock):
    """Return a list that receives the row passed to company_invitations.insert."""
    captured: list = []
    invitations = MagicMock()
    members_table = MagicMock()

    def table(name: str):
        if name == "company_invitations":
            return invitations
        if name == "company_members":
            return members_table
        return MagicMock()

    supabase.table.side_effect = table

    update_chain = invitations.update.return_value
    update_chain.eq.return_value = update_chain
    update_chain.is_.return_value = update_chain
    update_chain.execute.return_value = MagicMock(data=[])

    def insert(row):
        captured.append(row)
        result = MagicMock()
        result.data = [{**row, "id": "inv-1"}]
        chain = MagicMock()
        chain.execute.return_value = result
        return chain

    invitations.insert.side_effect = insert
    return captured, members_table


@pytest.mark.asyncio
async def test_e1_flag_off_invite_stores_general_and_list_omits_key():
    """E1: flag off → invite ignores sales_role; list/summary omit the key."""
    supabase = MagicMock()
    captured, _ = _capture_insert(supabase)
    svc = CompanyService(supabase)
    svc.ensure_seat_available = MagicMock()
    svc._email_exists_in_auth = MagicMock(return_value=None)
    svc.get_company = MagicMock(return_value={"name": "Acme"})
    svc._send_invite_email = AsyncMock(return_value=False)

    with patch("app.services.company.is_enabled", return_value=False):
        await svc.create_invite(
            company_id="co-1",
            email="a@b.com",
            role="member",
            sales_role="sdr",
            send_email=False,
        )
    assert captured[0]["sales_role"] == "general"

    with patch("app.services.company.is_enabled", return_value=False):
        svc.get_membership = MagicMock(return_value=_membership())
        svc.get_company = MagicMock(return_value={"name": "Acme"})
        svc.seat_usage = MagicMock(
            return_value={
                "seat_limit": 5,
                "seats_used": 1,
                "seats_pending": 0,
                "seats_active": 1,
            }
        )
        svc.billing_for = MagicMock(return_value={})
        out = svc.company_summary_for_user("u-owner")
    assert "sales_role" not in out


@pytest.mark.asyncio
async def test_e8_flag_on_invalid_invite_sales_role_400():
    """E8: invalid sales_role on invite → 400 with rejected value."""
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc.ensure_seat_available = MagicMock()

    with patch("app.services.company.is_enabled", return_value=True):
        with pytest.raises(HTTPException) as exc:
            await svc.create_invite(
                company_id="co-1",
                email="a@b.com",
                role="member",
                sales_role="nope",
                send_email=False,
            )
    assert exc.value.status_code == 400
    assert "nope" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_create_invite_flag_on_stores_sales_role():
    supabase = MagicMock()
    captured, _ = _capture_insert(supabase)
    svc = CompanyService(supabase)
    svc.ensure_seat_available = MagicMock()
    svc._email_exists_in_auth = MagicMock(return_value=None)
    svc.get_company = MagicMock(return_value={"name": "Acme"})
    svc._send_invite_email = AsyncMock(return_value=False)

    with patch("app.services.company.is_enabled", return_value=True):
        await svc.create_invite(
            company_id="co-1",
            email="a@b.com",
            role="member",
            sales_role="ae",
            send_email=False,
        )
    assert captured[0]["sales_role"] == "ae"


@pytest.mark.asyncio
async def test_create_invite_flag_on_default_general():
    supabase = MagicMock()
    captured, _ = _capture_insert(supabase)
    svc = CompanyService(supabase)
    svc.ensure_seat_available = MagicMock()
    svc._email_exists_in_auth = MagicMock(return_value=None)
    svc.get_company = MagicMock(return_value={"name": "Acme"})
    svc._send_invite_email = AsyncMock(return_value=False)

    with patch("app.services.company.is_enabled", return_value=True):
        await svc.create_invite(
            company_id="co-1",
            email="a@b.com",
            role="member",
            send_email=False,
        )
    assert captured[0]["sales_role"] == "general"


def test_e3_accept_invite_missing_sales_role_becomes_general():
    """E3: invite without sales_role (pre-flag) → member born as general."""
    supabase = MagicMock()
    captured_members: list = []
    svc = CompanyService(supabase)
    svc.get_invite_by_token = MagicMock(
        return_value={
            "id": "inv-1",
            "company_id": "co-1",
            "email": "new@b.com",
            "role": "member",
            # no sales_role key — invite created before flag
        }
    )
    svc._email_exists_in_auth = MagicMock(return_value=None)
    svc.get_membership = MagicMock(return_value=None)

    auth_client = MagicMock()
    auth_client.auth.sign_up.return_value = MagicMock(
        user=MagicMock(id="u-new")
    )

    def table(name: str):
        t = MagicMock()
        if name == "company_members":

            def insert(row):
                captured_members.append(row)
                r = MagicMock()
                r.data = [row]
                c = MagicMock()
                c.execute.return_value = r
                return c

            t.insert.side_effect = insert
        else:
            t.insert.return_value.execute.return_value = MagicMock(data=[{}])
            t.update.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{}]
            )
        return t

    supabase.table.side_effect = table

    svc.accept_invite(
        raw_token="tok",
        password="password1",
        full_name="New",
        auth_client=auth_client,
    )
    assert captured_members[0]["sales_role"] == "general"


def test_e4_accept_invite_unknown_sales_role_becomes_general():
    """E4: unknown stored value → treated as general on accept / read."""
    supabase = MagicMock()
    captured_members: list = []
    svc = CompanyService(supabase)
    svc.get_invite_by_token = MagicMock(
        return_value={
            "id": "inv-1",
            "company_id": "co-1",
            "email": "new@b.com",
            "role": "member",
            "sales_role": "manipulated",
        }
    )
    svc._email_exists_in_auth = MagicMock(return_value=None)

    auth_client = MagicMock()
    auth_client.auth.sign_up.return_value = MagicMock(
        user=MagicMock(id="u-new")
    )

    def table(name: str):
        t = MagicMock()
        if name == "company_members":

            def insert(row):
                captured_members.append(row)
                r = MagicMock()
                r.data = [row]
                c = MagicMock()
                c.execute.return_value = r
                return c

            t.insert.side_effect = insert
        else:
            t.insert.return_value.execute.return_value = MagicMock(data=[{}])
            t.update.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{}]
            )
        return t

    supabase.table.side_effect = table

    svc.accept_invite(
        raw_token="tok",
        password="password1",
        full_name="New",
        auth_client=auth_client,
    )
    assert captured_members[0]["sales_role"] == "general"


def test_accept_invite_copies_valid_sales_role():
    supabase = MagicMock()
    captured_members: list = []
    svc = CompanyService(supabase)
    svc.get_invite_by_token = MagicMock(
        return_value={
            "id": "inv-1",
            "company_id": "co-1",
            "email": "new@b.com",
            "role": "member",
            "sales_role": "sdr",
        }
    )
    svc._email_exists_in_auth = MagicMock(return_value=None)
    auth_client = MagicMock()
    auth_client.auth.sign_up.return_value = MagicMock(user=MagicMock(id="u-new"))

    def table(name: str):
        t = MagicMock()
        if name == "company_members":

            def insert(row):
                captured_members.append(row)
                r = MagicMock()
                r.data = [row]
                c = MagicMock()
                c.execute.return_value = r
                return c

            t.insert.side_effect = insert
        else:
            t.insert.return_value.execute.return_value = MagicMock(data=[{}])
            t.update.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{}]
            )
        return t

    supabase.table.side_effect = table
    svc.accept_invite(
        raw_token="tok", password="password1", full_name="New", auth_client=auth_client
    )
    assert captured_members[0]["sales_role"] == "sdr"


def test_e2_e4_list_members_normalizes_and_includes_when_flag_on():
    """E2/E4: flag on → sales_role present; unknown → general."""
    supabase = MagicMock()
    svc = CompanyService(supabase)
    members_result = MagicMock()
    members_result.data = [
        {
            "id": "m1",
            "user_id": "u1",
            "role": "member",
            "status": "active",
            "created_at": "t",
            "sales_role": "general",
        },
        {
            "id": "m2",
            "user_id": "u2",
            "role": "member",
            "status": "active",
            "created_at": "t",
            "sales_role": "weird",
        },
    ]
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.order.return_value = chain
    chain.execute.return_value = members_result

    profiles = MagicMock()
    profiles.select.return_value.in_.return_value.execute.return_value = MagicMock(
        data=[]
    )

    def table(name: str):
        if name == "company_members":
            return chain
        if name == "user_profiles":
            return profiles
        return MagicMock()

    supabase.table.side_effect = table
    svc._auth_emails_by_ids = MagicMock(return_value={"u1": "a@b.com", "u2": "c@d.com"})

    with patch("app.services.company.is_enabled", return_value=True):
        out = svc.list_members("co-1")
    assert out[0]["sales_role"] == "general"
    assert out[1]["sales_role"] == "general"


def test_e1_list_members_omits_sales_role_when_flag_off():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    members_result = MagicMock()
    members_result.data = [
        {
            "id": "m1",
            "user_id": "u1",
            "role": "member",
            "status": "active",
            "created_at": "t",
            "sales_role": "sdr",
        },
    ]
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.order.return_value = chain
    chain.execute.return_value = members_result
    profiles = MagicMock()
    profiles.select.return_value.in_.return_value.execute.return_value = MagicMock(
        data=[]
    )

    def table(name: str):
        if name == "company_members":
            return chain
        if name == "user_profiles":
            return profiles
        return MagicMock()

    supabase.table.side_effect = table
    svc._auth_emails_by_ids = MagicMock(return_value={"u1": "a@b.com"})

    with patch("app.services.company.is_enabled", return_value=False):
        out = svc.list_members("co-1")
    assert "sales_role" not in out[0]


def test_list_pending_invites_flag_on_includes_sales_role():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.is_.return_value = chain
    chain.gt.return_value = chain
    chain.order.return_value = chain
    chain.execute.return_value = MagicMock(
        data=[
            {
                "id": "i1",
                "email": "x@y.com",
                "role": "member",
                "expires_at": "e",
                "created_at": "c",
                "invited_by": "u",
                "sales_role": "ae",
            }
        ]
    )
    supabase.table.return_value = chain

    with patch("app.services.company.is_enabled", return_value=True):
        out = svc.list_pending_invites("co-1")
    assert out[0]["sales_role"] == "ae"


def test_company_summary_flag_on_includes_normalized_sales_role():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc.get_membership = MagicMock(
        return_value=_membership(sales_role="SDR")  # invalid casing → general
    )
    # Override after normalize in summary — Membership holds raw; summary normalizes
    m = _membership(sales_role="sdr")
    svc.get_membership = MagicMock(return_value=m)
    svc.get_company = MagicMock(return_value={"name": "Acme"})
    svc.seat_usage = MagicMock(
        return_value={
            "seat_limit": 3,
            "seats_used": 1,
            "seats_pending": 0,
            "seats_active": 1,
        }
    )
    svc.billing_for = MagicMock(return_value={})

    with patch("app.services.company.is_enabled", return_value=True):
        out = svc.company_summary_for_user("u-owner")
    assert out["sales_role"] == "sdr"


def test_company_summary_unknown_sales_role_is_general():
    """E4: unknown column value never breaks session — becomes general."""
    supabase = MagicMock()
    svc = CompanyService(supabase)
    svc.get_membership = MagicMock(return_value=_membership(sales_role="nope"))
    svc.get_company = MagicMock(return_value={"name": "Acme"})
    svc.seat_usage = MagicMock(
        return_value={
            "seat_limit": 3,
            "seats_used": 1,
            "seats_pending": 0,
            "seats_active": 1,
        }
    )
    svc.billing_for = MagicMock(return_value={})

    with patch("app.services.company.is_enabled", return_value=True):
        out = svc.company_summary_for_user("u-owner")
    assert out["sales_role"] == "general"


def test_e6_e7_update_sales_role_does_not_change_role():
    """E6/E7: admin/owner can set sales_role; permission role unchanged."""
    supabase = MagicMock()
    svc = CompanyService(supabase)
    target = {
        "id": "m-owner",
        "user_id": "u-owner",
        "role": "owner",
        "status": "active",
        "sales_role": "general",
    }
    svc._get_member_row = MagicMock(return_value=target)

    update_payloads: list = []
    chain = MagicMock()

    def update(payload):
        update_payloads.append(payload)
        c = MagicMock()
        c.eq.return_value = c
        c.execute.return_value = MagicMock(
            data=[{**target, **payload, "role": "owner", "status": "active"}]
        )
        return c

    chain.update.side_effect = update
    supabase.table.return_value = chain

    updated = svc.update_member_sales_role(
        company_id="co-1",
        member_id="m-owner",
        sales_role="sdr",
    )
    assert update_payloads[0]["sales_role"] == "sdr"
    assert "role" not in update_payloads[0]
    assert "status" not in update_payloads[0]
    assert updated["role"] == "owner"


def test_e9_update_sales_role_disabled_does_not_reactivate():
    """E9: changing sales_role of disabled member does not reactivate."""
    supabase = MagicMock()
    svc = CompanyService(supabase)
    target = {
        "id": "m-d",
        "user_id": "u-d",
        "role": "member",
        "status": "disabled",
        "sales_role": "general",
    }
    svc._get_member_row = MagicMock(return_value=target)
    update_payloads: list = []
    chain = MagicMock()

    def update(payload):
        update_payloads.append(payload)
        c = MagicMock()
        c.eq.return_value = c
        c.execute.return_value = MagicMock(
            data=[{**target, **payload, "status": "disabled"}]
        )
        return c

    chain.update.side_effect = update
    supabase.table.return_value = chain

    updated = svc.update_member_sales_role(
        company_id="co-1", member_id="m-d", sales_role="ae"
    )
    assert "status" not in update_payloads[0]
    assert updated["status"] == "disabled"


def test_update_sales_role_invalid_400():
    supabase = MagicMock()
    svc = CompanyService(supabase)
    with pytest.raises(HTTPException) as exc:
        svc.update_member_sales_role(
            company_id="co-1", member_id="m1", sales_role="nope"
        )
    assert exc.value.status_code == 400
    assert "nope" in str(exc.value.detail)


def test_e10_last_write_wins():
    """E10: two sequential updates — last write wins."""
    supabase = MagicMock()
    svc = CompanyService(supabase)
    target = {
        "id": "m1",
        "user_id": "u1",
        "role": "member",
        "status": "active",
        "sales_role": "general",
    }
    svc._get_member_row = MagicMock(return_value=target)
    payloads: list = []
    chain = MagicMock()

    def update(payload):
        payloads.append(payload)
        c = MagicMock()
        c.eq.return_value = c
        c.execute.return_value = MagicMock(data=[{**target, **payload}])
        return c

    chain.update.side_effect = update
    supabase.table.return_value = chain

    svc.update_member_sales_role(company_id="co-1", member_id="m1", sales_role="sdr")
    svc.update_member_sales_role(company_id="co-1", member_id="m1", sales_role="ae")
    assert payloads[-1]["sales_role"] == "ae"


def test_e12_remove_member_deletes_row():
    """E12: removing a member deletes the company_members row (role goes with it)."""
    supabase = MagicMock()
    svc = CompanyService(supabase)
    target = {
        "id": "m2",
        "user_id": "u2",
        "role": "member",
        "status": "active",
        "sales_role": "sdr",
    }
    svc._get_member_row = MagicMock(return_value=target)
    actor = _membership(role="owner", user_id="u-owner")

    delete_chain = MagicMock()
    delete_chain.eq.return_value = delete_chain
    delete_chain.execute.return_value = MagicMock(data=[target])

    profile_chain = MagicMock()
    profile_chain.update.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{}]
    )

    def table(name: str):
        if name == "company_members":
            t = MagicMock()
            t.delete.return_value = delete_chain
            return t
        if name == "user_profiles":
            return profile_chain
        return MagicMock()

    supabase.table.side_effect = table
    svc.remove_member(company_id="co-1", member_id="m2", actor=actor)
    supabase.table.assert_any_call("company_members")
    assert delete_chain.eq.called


@pytest.mark.asyncio
async def test_e11_invite_does_not_require_crm_owner():
    """E11: sales_role is stored without CRM owner matching."""
    supabase = MagicMock()
    captured, _ = _capture_insert(supabase)
    svc = CompanyService(supabase)
    svc.ensure_seat_available = MagicMock()
    svc._email_exists_in_auth = MagicMock(return_value=None)
    svc.get_company = MagicMock(return_value={"name": "Acme"})
    svc._send_invite_email = AsyncMock(return_value=False)

    with patch("app.services.company.is_enabled", return_value=True):
        await svc.create_invite(
            company_id="co-1",
            email="unknown-in-crm@b.com",
            role="member",
            sales_role="sdr",
            send_email=False,
        )
    assert captured[0]["sales_role"] == "sdr"
    assert captured[0]["email"] == "unknown-in-crm@b.com"


def _company_client(user_id: str, membership: Membership, supabase=None) -> TestClient:
    app = FastAPI()
    app.include_router(company_api.router)
    sb = supabase or MagicMock()
    app.dependency_overrides[get_user_id] = lambda: user_id
    app.dependency_overrides[get_supabase] = lambda: sb
    return TestClient(app)


def test_e5_member_patch_sales_role_403():
    """E5: member cannot PATCH sales-role."""
    supabase = MagicMock()
    svc_membership = _membership(role="member", user_id="u-member", member_id="m-mem")

    with patch.object(CompanyService, "require_manage_role") as require_manage:
        require_manage.side_effect = HTTPException(
            status_code=403, detail="Insufficient permissions"
        )
        with patch.object(CompanyService, "require_membership", return_value=svc_membership):
            client = _company_client("u-member", svc_membership, supabase)
            # Patch require_manage_role on instances via the class side_effect above
            resp = client.patch(
                "/api/v1/company/members/m-other/sales-role",
                json={"sales_role": "sdr"},
            )
    assert resp.status_code == 403


def test_e6_admin_can_patch_owner_sales_role():
    """E6: admin may change owner's sales_role."""
    supabase = MagicMock()
    admin = _membership(role="admin", user_id="u-admin", member_id="m-admin")

    with patch.object(CompanyService, "require_manage_role", return_value=admin):
        with patch.object(
            CompanyService,
            "update_member_sales_role",
            return_value={
                "id": "m-owner",
                "role": "owner",
                "status": "active",
                "sales_role": "ae",
            },
        ) as upd:
            client = _company_client("u-admin", admin, supabase)
            resp = client.patch(
                "/api/v1/company/members/m-owner/sales-role",
                json={"sales_role": "ae"},
            )
    assert resp.status_code == 200
    assert resp.json()["sales_role"] == "ae"
    upd.assert_called_once()
    assert upd.call_args.kwargs["member_id"] == "m-owner"
    assert upd.call_args.kwargs["sales_role"] == "ae"


def test_e7_owner_can_set_own_sales_role():
    """E7: owner can set themselves to sdr; permission role unchanged."""
    supabase = MagicMock()
    owner = _membership(role="owner", user_id="u-owner", member_id="m-owner")

    with patch.object(CompanyService, "require_manage_role", return_value=owner):
        with patch.object(
            CompanyService,
            "update_member_sales_role",
            return_value={
                "id": "m-owner",
                "role": "owner",
                "status": "active",
                "sales_role": "sdr",
            },
        ):
            client = _company_client("u-owner", owner, supabase)
            resp = client.patch(
                "/api/v1/company/members/m-owner/sales-role",
                json={"sales_role": "sdr"},
            )
    assert resp.status_code == 200
    body = resp.json()
    assert body["sales_role"] == "sdr"
    assert body.get("role", "owner") == "owner" or "role" not in body or body["role"] == "owner"


def test_get_members_includes_sales_roles_enabled():
    supabase = MagicMock()
    owner = _membership(role="owner", user_id="u-owner")

    with patch.object(CompanyService, "require_membership", return_value=owner):
        with patch.object(CompanyService, "list_members", return_value=[]):
            with patch.object(CompanyService, "list_pending_invites", return_value=[]):
                with patch(
                    "app.api.company.is_enabled", return_value=True
                ) as flag:
                    client = _company_client("u-owner", owner, supabase)
                    resp = client.get("/api/v1/company/members")
    assert resp.status_code == 200
    assert resp.json()["sales_roles_enabled"] is True
    flag.assert_called()


def test_company_summary_model_omits_sales_role_key_when_unset():
    """E1: CompanySummary JSON must not contain sales_role when flag off."""
    from app.api.auth import CompanySummary

    summary = CompanySummary(
        id="co-1",
        name="Acme",
        role="owner",
        seat_limit=1,
        seats_used=1,
        seats_pending=0,
    )
    assert "sales_role" not in summary.model_dump(mode="json")

    with_role = CompanySummary(
        id="co-1",
        name="Acme",
        role="owner",
        seat_limit=1,
        seats_used=1,
        seats_pending=0,
        sales_role="sdr",
    )
    assert with_role.model_dump(mode="json")["sales_role"] == "sdr"
