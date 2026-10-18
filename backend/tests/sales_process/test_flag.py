from app.config import settings
from app.services.feature_flags import CLIENT_FLAGS, PROCESS_FLAGS


def test_the_sales_process_is_on_for_every_company_and_reaches_the_frontend():
    assert PROCESS_FLAGS == ("SALES_PROCESS_ENABLED",)
    assert "SALES_PROCESS_ENABLED" in CLIENT_FLAGS
    # On for everyone since 18 Oct 2026 (Toni); a company can still be switched off in company_feature_flags.
    assert settings.SALES_PROCESS_ENABLED is True
