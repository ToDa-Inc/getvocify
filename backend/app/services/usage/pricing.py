"""Turn usage into dollars. LLM cost comes from the vendor; STT cost is audio time x rate."""

from __future__ import annotations

from typing import Optional

from app.config import settings

# (provider, mode, tier) -> settings field holding the USD/hour list price
_STT_RATES = {
    ("speechmatics", "realtime", "enhanced"): "STT_RATE_SPEECHMATICS_REALTIME_ENHANCED_USD_HR",
    ("speechmatics", "realtime", "standard"): "STT_RATE_SPEECHMATICS_REALTIME_STANDARD_USD_HR",
    ("speechmatics", "batch", "enhanced"): "STT_RATE_SPEECHMATICS_BATCH_ENHANCED_USD_HR",
    ("speechmatics", "batch", "standard"): "STT_RATE_SPEECHMATICS_BATCH_STANDARD_USD_HR",
    ("deepgram", "batch", ""): "STT_RATE_DEEPGRAM_BATCH_USD_HR",
}


def stt_rate_usd_per_hour(provider: str, mode: str, tier: str = "") -> Optional[float]:
    name = _STT_RATES.get((provider, mode, tier if provider == "speechmatics" else ""))
    return getattr(settings, name, None) if name else None


def stt_cost_usd(
    provider: str, mode: str, seconds: float, channels: int = 1, tier: str = ""
) -> Optional[float]:
    """None when there is no rate for this provider/mode/tier: unpriced beats a made-up number."""
    rate = stt_rate_usd_per_hour(provider, mode, tier)
    if rate is None or seconds <= 0:
        return None
    billed = max(1, channels) if settings.STT_BILL_PER_CHANNEL else 1
    return round(seconds / 3600.0 * rate * billed, 6)
