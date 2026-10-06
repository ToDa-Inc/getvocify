from app.services.sales_role import SALES_ROLE_VALUES, normalize_sales_role


def test_normalize_valid_roles():
    assert normalize_sales_role("sdr") == "sdr"
    assert normalize_sales_role("ae") == "ae"
    assert normalize_sales_role("general") == "general"


def test_normalize_invalid_roles_become_general():
    assert normalize_sales_role(None) == "general"
    assert normalize_sales_role("") == "general"
    assert normalize_sales_role("owner") == "general"
    assert normalize_sales_role("SDR") == "general"


def test_sales_role_values():
    assert SALES_ROLE_VALUES == frozenset({"sdr", "ae", "general"})
