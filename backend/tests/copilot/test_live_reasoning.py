from app.config import settings
from app.services.copilot.suggest import live_reasoning


def test_live_help_does_not_reason_by_default(monkeypatch):
    # Only an effort is sent, never `enabled: false` (models with mandatory reasoning reject it).
    monkeypatch.setattr(settings, "COPILOT_REASONING_EFFORT", None, raising=False)
    assert "enabled" not in live_reasoning()["reasoning"]
    assert live_reasoning() == {"reasoning": {"effort": "none"}}
