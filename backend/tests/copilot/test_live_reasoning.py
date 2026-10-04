from app.services.copilot.suggest import LIVE_REASONING


def test_live_help_never_switches_reasoning_off():
    # Models with mandatory reasoning reject `enabled: false` on every request.
    assert "enabled" not in LIVE_REASONING["reasoning"]
    assert LIVE_REASONING == {"reasoning": {"effort": "minimal"}}
