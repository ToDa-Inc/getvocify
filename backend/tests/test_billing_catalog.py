from app.services.billing.catalog import (
    catalog_payload,
    plan_from_product_id,
    product_id_for,
    yearly_discount_percent,
)


def test_product_ids_match_live_catalog():
    assert product_id_for("starter", "monthly") == "prod_VENfYYKhSV2KAB"
    assert product_id_for("pro", "monthly") == "prod_VENfWDk6BSnMIy"
    assert product_id_for("starter", "yearly") == "prod_VENgF43xTwG3OT"
    assert product_id_for("pro", "yearly") == "prod_VENgP2K1H6YO7c"


def test_plan_from_product_id():
    assert plan_from_product_id("prod_VENfWDk6BSnMIy") == "pro"
    assert plan_from_product_id("prod_VENgF43xTwG3OT") == "starter"
    assert plan_from_product_id("prod_unknown") is None


def test_catalog_payload_has_pro_dialer():
    payload = catalog_payload()
    starter, pro = payload["plans"]
    assert starter["monthly_amount"] == 30
    assert starter["yearly_amount"] == 300
    assert starter["yearly_monthly_amount"] == 25
    assert starter["yearly_discount_percent"] == 17
    assert pro["monthly_amount"] == 50
    assert pro["yearly_amount"] == 500
    assert pro["yearly_monthly_amount"] == 42
    assert pro["yearly_discount_percent"] == 17
    assert payload["yearly_discount_percent"] == 17
    assert yearly_discount_percent(30, 300) == 17
    assert yearly_discount_percent(50, 500) == 17
    assert pro["includes_dialer"] is True
    assert pro["dialer_minutes"] == 1000
    assert "Dialer included — 1,000 minutes" in pro["features"]
    assert starter["includes_dialer"] is False
