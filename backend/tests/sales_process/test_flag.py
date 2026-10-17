from app.config import settings
from app.services.feature_flags import CLIENT_FLAGS, PROCESS_FLAGS


def test_the_sales_process_ships_dark_and_reaches_the_frontend():
    assert PROCESS_FLAGS == ("SALES_PROCESS_ENABLED",)
    assert "SALES_PROCESS_ENABLED" in CLIENT_FLAGS
    assert settings.SALES_PROCESS_ENABLED is False
