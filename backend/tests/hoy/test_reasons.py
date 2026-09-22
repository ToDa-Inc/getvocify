"""F06: reasons stay short and come from one server-side writer."""

from datetime import datetime, timezone

from app.services.hoy.reasons import reason
from app.services.hoy.signals import Signal

NOW = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc)


def _cold() -> Signal:
    return Signal(
        type="going_cold",
        contact_id="42",
        deal_id=None,
        source_memo_id="memo-1",
        due_at=None,
        payload={"interest": "high", "days_silent": 12},
        dedupe_key="cold:42",
        connection_id="crm-A",
    )


def test_reasons_are_short_and_match_lang_without_diverging_facts():
    cold = _cold()
    es = reason(cold, lang="es")
    en = reason(cold, lang="en")
    assert len(es) <= 120
    assert len(en) <= 120
    assert "12" in es and "12" in en
    assert es != en
