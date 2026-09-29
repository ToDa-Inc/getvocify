import pytest

from app.services.crm_copilot import crm_analytics


@pytest.fixture(autouse=True)
def _no_search_pacing(monkeypatch):
    """The pacing protects HubSpot's per-second limit; tests use in-memory clients and must not wait for it."""
    monkeypatch.setattr(crm_analytics, "SEARCH_INTERVAL", 0.0)
    monkeypatch.setattr(crm_analytics, "RETRY_BACKOFF", 0.0)


@pytest.fixture(autouse=True)
def _no_effort_routing_network(monkeypatch):
    """Routing an ambiguous question may ask Jev over the network. Tests decide effort explicitly instead."""
    from app.config import settings

    monkeypatch.setattr(settings, "ASK_EFFORT_ROUTING", False)
