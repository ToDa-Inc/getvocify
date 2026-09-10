from datetime import datetime, timedelta, timezone

from app.services.billing.entitlement import (
    PAST_DUE_GRACE,
    billing_row_from_subscription,
    can_use_dialer,
    company_id_from_stripe_object,
    is_paywalled,
    normalize_billing_status,
    should_sync_seat_limit,
    subscription_interval,
    subscription_period_end,
    subscription_plan_type,
    subscription_quantity,
)

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)


def test_open_and_unlocked_are_never_paywalled():
    assert is_paywalled({"access_mode": "open"}, {"billing_status": "none"}) is False
    assert is_paywalled({"access_mode": "unlocked"}, {"billing_status": "canceled"}) is False
    assert is_paywalled(None) is False


def test_paywalled_without_active_sub_locks():
    company = {"access_mode": "paywalled"}
    assert is_paywalled(company, {"billing_status": "none"}) is True
    assert is_paywalled(company, {"billing_status": "canceled"}) is True
    assert is_paywalled(company, {"billing_status": "past_due"}) is True


def test_paywalled_with_paid_sub_is_open():
    company = {"access_mode": "paywalled"}
    assert is_paywalled(company, {"billing_status": "active"}) is False
    assert is_paywalled(company, {"billing_status": "trialing"}) is False


def test_past_due_grace_holds_then_locks():
    company = {"access_mode": "paywalled"}
    since = (NOW - timedelta(days=1)).isoformat()
    assert (
        is_paywalled(
            company,
            {"billing_status": "past_due", "past_due_since": since},
            now=NOW,
        )
        is False
    )
    expired = (NOW - PAST_DUE_GRACE - timedelta(minutes=1)).isoformat()
    assert (
        is_paywalled(
            company,
            {"billing_status": "past_due", "past_due_since": expired},
            now=NOW,
        )
        is True
    )


def test_missing_access_mode_defaults_open():
    assert is_paywalled({}, {"billing_status": "none"}) is False


def test_subscription_quantity_interval_and_period():
    sub = {
        "id": "sub_1",
        "status": "active",
        "current_period_end": int(NOW.timestamp()),
        "items": {
            "data": [
                {
                    "id": "si_1",
                    "quantity": 8,
                    "price": {"recurring": {"interval": "year"}},
                }
            ]
        },
    }
    assert subscription_quantity(sub) == 8
    assert subscription_interval(sub) == "yearly"
    assert subscription_period_end(sub) == NOW


def test_subscription_quantity_floor_is_one():
    assert subscription_quantity({"items": {"data": [{"quantity": 0}]}}) == 1
    assert subscription_quantity({}) == 1


def test_billing_row_sets_snapshot_not_seats():
    row = billing_row_from_subscription(
        {
            "id": "sub_1",
            "status": "active",
            "customer": "cus_1",
            "cancel_at_period_end": False,
            "current_period_end": int(NOW.timestamp()),
            "items": {
                "data": [
                    {
                        "quantity": 5,
                        "price": {
                            "product": "prod_VENfYYKhSV2KAB",
                            "recurring": {"interval": "month"},
                        },
                    }
                ]
            },
        },
        now=NOW,
    )
    assert row["stripe_customer_id"] == "cus_1"
    assert row["billing_status"] == "active"
    assert row["billing_interval"] == "monthly"
    assert row["plan_type"] == "starter"
    assert row["quantity"] == 5
    assert row["current_period_end"] == NOW.isoformat()
    assert row["past_due_since"] is None
    assert "seat_limit" not in row


def test_past_due_since_is_sticky():
    first = billing_row_from_subscription(
        {"id": "sub_1", "status": "past_due", "items": {"data": [{"quantity": 2}]}},
        now=NOW,
    )
    later = billing_row_from_subscription(
        {"id": "sub_1", "status": "past_due", "items": {"data": [{"quantity": 2}]}},
        existing=first,
        now=NOW + timedelta(days=1),
    )
    assert first["past_due_since"] == NOW.isoformat()
    assert later["past_due_since"] == first["past_due_since"]


def test_should_sync_seats_never_for_flat_plans():
    row = {"billing_status": "active"}
    assert should_sync_seat_limit({"access_mode": "open"}, row) is False
    assert should_sync_seat_limit({"access_mode": "unlocked"}, row) is False
    assert should_sync_seat_limit({"access_mode": "paywalled"}, row) is False


def test_plan_type_prefers_metadata():
    assert (
        subscription_plan_type(
            {
                "metadata": {"plan_type": "pro"},
                "items": {"data": [{"price": {"product": "prod_VENfYYKhSV2KAB"}}]},
            }
        )
        == "pro"
    )


def test_can_use_dialer():
    open_company = {"access_mode": "open"}
    assert can_use_dialer(open_company, {"billing_status": "none"}) is True
    assert can_use_dialer(open_company, {"billing_status": "active", "plan_type": "starter"}) is False
    assert can_use_dialer(open_company, {"billing_status": "active", "plan_type": "pro"}) is True
    assert can_use_dialer({"access_mode": "unlocked"}, {"billing_status": "none"}) is True
    assert can_use_dialer({"access_mode": "paywalled"}, {"billing_status": "active", "plan_type": "starter"}) is False
    assert can_use_dialer({"access_mode": "paywalled"}, {"billing_status": "active", "plan_type": "pro"}) is True


def test_deleted_row_is_canceled():
    row = billing_row_from_subscription(
        {"id": "sub_1", "status": "canceled", "items": {"data": [{"quantity": 3}]}},
        deleted=True,
        existing={"quantity": 3},
    )
    assert row["billing_status"] == "canceled"
    assert row["quantity"] == 3


def test_normalize_stripe_statuses():
    assert normalize_billing_status("paused") == "unpaid"
    assert normalize_billing_status("incomplete_expired") == "canceled"
    assert normalize_billing_status("nope") == "none"


def test_company_id_from_metadata_or_reference():
    assert company_id_from_stripe_object({"metadata": {"company_id": "c1"}}) == "c1"
    assert company_id_from_stripe_object({"client_reference_id": "c2"}) == "c2"
