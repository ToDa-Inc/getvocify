from app.config import settings
from app.services.copilot.suggest import live_reasoning


def test_live_help_never_switches_reasoning_off(monkeypatch):
    # Models with mandatory reasoning reject `enabled: false` on every request: only an effort is sent.
    monkeypatch.setattr(settings, "COPILOT_REASONING_EFFORT", None, raising=False)
    assert "enabled" not in live_reasoning()["reasoning"]
    assert live_reasoning() == {"reasoning": {"effort": "minimal"}}
