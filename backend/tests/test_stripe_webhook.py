from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.stripe_webhooks import router as stripe_router
from app.deps import get_supabase
from app.paywall import path_is_exempt
from app.services.billing.store import apply_subscription, claim_event, resolve_company


def test_path_is_exempt():
    assert path_is_exempt("/api/v1/billing/status") is True
    assert path_is_exempt("/api/v1/auth/me") is True
    assert path_is_exempt("/webhooks/stripe") is True
    assert path_is_exempt("/api/v1/memos") is False
    assert path_is_exempt("/api/v1/company") is False


def test_claim_event_skips_duplicates():
    supabase = MagicMock()
    supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"id": "evt_1"}]
    )
    assert claim_event(supabase, "evt_1", "invoice.paid") is False


def test_claim_event_inserts_new():
    supabase = MagicMock()
    supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[]
    )
    supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{"id": "evt_2"}])
    assert claim_event(supabase, "evt_2", "checkout.session.completed") is True


def test_resolve_company_from_metadata():
    supabase = MagicMock()
    supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"id": "c1", "access_mode": "open"}]
    )
    found = resolve_company(supabase, {"metadata": {"company_id": "c1"}})
    assert found["id"] == "c1"


class _Tables:
    def __init__(self):
        self.billing_upserts = []
        self.company_updates = []

    def __call__(self, name: str):
        chain = MagicMock()
        if name == "company_billing":
            chain.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[]
            )

            def _upsert(row, on_conflict=None):
                self.billing_upserts.append(row)
                chain._upsert_row = row
                return chain

            chain.upsert.side_effect = _upsert
            chain.execute.return_value = MagicMock(data=[{}])
        elif name == "companies":
            def _update(row):
                self.company_updates.append(row)
                return chain

            chain.update.side_effect = _update
            chain.eq.return_value.execute.return_value = MagicMock(data=[{}])
        else:
            chain.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[]
            )
            chain.insert.return_value.execute.return_value = MagicMock(data=[{}])
        return chain


def test_apply_subscription_writes_billing_and_seats():
    tables = _Tables()
    supabase = MagicMock()
    supabase.table.side_effect = tables
    company = {"id": "c1", "access_mode": "open"}
    sub = {
        "id": "sub_1",
        "status": "active",
        "customer": "cus_1",
        "items": {"data": [{"quantity": 4, "price": {"recurring": {"interval": "month"}}}]},
    }
    apply_subscription(supabase, company, sub)
    assert tables.billing_upserts[0]["billing_status"] == "active"
    assert tables.billing_upserts[0]["quantity"] == 4
    assert tables.company_updates == []


def test_apply_subscription_skips_seats_when_unlocked():
    tables = _Tables()
    supabase = MagicMock()
    supabase.table.side_effect = tables
    apply_subscription(
        supabase,
        {"id": "c1", "access_mode": "unlocked"},
        {
            "id": "sub_1",
            "status": "active",
            "items": {"data": [{"quantity": 2, "price": {"recurring": {"interval": "month"}}}]},
        },
    )
    assert tables.billing_upserts
    assert tables.company_updates == []


def _client(supabase, event):
    app = FastAPI()
    app.include_router(stripe_router, prefix="/webhooks")
    app.dependency_overrides[get_supabase] = lambda: supabase

    class _Stripe:
        def verify_webhook(self, payload, signature):
            return event

        def retrieve_subscription(self, sub_id):
            return {
                "id": sub_id,
                "status": "active",
                "customer": "cus_1",
                "metadata": {"company_id": "c1"},
                "items": {"data": [{"quantity": 3, "price": {"recurring": {"interval": "month"}}}]},
            }

    with patch("app.api.stripe_webhooks.StripeService", return_value=_Stripe()):
        yield TestClient(app)


def test_webhook_rejects_missing_signature():
    app = FastAPI()
    app.include_router(stripe_router, prefix="/webhooks")
    app.dependency_overrides[get_supabase] = lambda: MagicMock()
    client = TestClient(app)
    res = client.post("/webhooks/stripe", content=b"{}")
    assert res.status_code == 400


def test_webhook_subscription_updated_applies_then_claims():
    tables = _Tables()
    supabase = MagicMock()

    def table(name: str):
        if name == "stripe_webhook_events":
            chain = MagicMock()
            chain.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[]
            )
            chain.insert.return_value.execute.return_value = MagicMock(data=[{}])
            return chain
        if name == "companies" and not tables.company_updates:
            chain = MagicMock()
            chain.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[{"id": "c1", "access_mode": "open"}]
            )

            def _update(row):
                tables.company_updates.append(row)
                return chain

            chain.update.side_effect = _update
            chain.eq.return_value.execute.return_value = MagicMock(data=[{}])
            return chain
        return tables(name)

    supabase.table.side_effect = table
    event = {
        "id": "evt_sub",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_1",
                "status": "active",
                "customer": "cus_1",
                "metadata": {"company_id": "c1"},
                "items": {"data": [{"quantity": 6, "price": {"recurring": {"interval": "year"}}}]},
            }
        },
    }
    for client in _client(supabase, event):
        res = client.post("/webhooks/stripe", content=b"{}", headers={"stripe-signature": "t=1,v1=x"})
        assert res.status_code == 200
        assert res.json()["event_type"] == "customer.subscription.updated"
        assert tables.billing_upserts[0]["quantity"] == 6
        assert tables.billing_upserts[0]["billing_interval"] == "yearly"
        assert tables.company_updates == []


def test_webhook_apply_failure_does_not_claim():
    supabase = MagicMock()
    events = MagicMock()
    events.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
    inserted = []

    def table(name: str):
        if name == "stripe_webhook_events":
            events.insert.side_effect = lambda row: inserted.append(row) or events
            return events
        raise RuntimeError("apply boom")

    supabase.table.side_effect = table
    event = {
        "id": "evt_fail",
        "type": "customer.subscription.updated",
        "data": {"object": {"id": "sub_1", "metadata": {"company_id": "c1"}}},
    }
    for client in _client(supabase, event):
        res = client.post("/webhooks/stripe", content=b"{}", headers={"stripe-signature": "t=1,v1=x"})
        assert res.status_code == 500
        assert inserted == []
