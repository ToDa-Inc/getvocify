"""Billing checkout routes plan switches through Stripe confirmation."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.billing.stripe_service import StripeService


@patch("app.services.billing.stripe_service.settings.STRIPE_SECRET_KEY", "sk_test_x")
@patch("app.services.billing.stripe_service.stripe.billing_portal.Session.create")
def test_subscription_update_portal_session_uses_confirm_flow(mock_create):
    mock_create.return_value = MagicMock(url="https://billing.stripe.com/session/test")

    url = StripeService().create_subscription_update_portal_session(
        customer_id="cus_123",
        return_url="https://app.getvocify.com/dashboard/settings/billing?billing=success",
        subscription_id="sub_123",
        subscription_item_id="si_123",
        price_id="price_456",
    )

    assert url == "https://billing.stripe.com/session/test"
    mock_create.assert_called_once()
    kwargs = mock_create.call_args.kwargs
    assert kwargs["customer"] == "cus_123"
    assert kwargs["flow_data"]["type"] == "subscription_update_confirm"
    assert kwargs["flow_data"]["subscription_update_confirm"]["subscription"] == "sub_123"
    items = kwargs["flow_data"]["subscription_update_confirm"]["items"]
    assert items[0]["id"] == "si_123"
    assert items[0]["price"] == "price_456"
    assert items[0]["quantity"] == 1
