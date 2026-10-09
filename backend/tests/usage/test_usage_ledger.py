from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from app.services.llm.providers.openrouter import OPENROUTER_URL, OpenRouterProvider, openrouter_call_meta
from app.services.usage import flush, record_llm_usage, record_stt_usage, scoped, usage_scope
from app.services.usage import ledger
from app.services.usage.pricing import stt_cost_usd
_REAL_WRITE = ledger._write  # captured before the autouse fixture stubs it
from app.services.usage.report import memo_cost_report, period_summary


@pytest.fixture
def events():
    """Events the ledger would write, without a database."""
    captured = []
    with patch("app.services.usage.ledger._write", side_effect=captured.append):
        yield captured


def test_openrouter_meta_carries_billed_cost_and_token_details():
    meta = openrouter_call_meta(
        {"model": "m", "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0123}},
        requested_model="x",
    )
    assert (meta["cost_usd"], meta["prompt_tokens"]) == (0.0123, 10)


def test_llm_event_takes_purpose_and_memo_from_the_scope(events):
    with usage_scope("extract", user_id="u1", memo_id="m1"):
        record_llm_usage("openrouter", {"prompt_tokens": 7, "completion_tokens": 2, "cost_usd": 0.5})
    e = events[0]
    assert (e.purpose, e.memo_id, e.user_id, e.cost_usd, e.prompt_tokens) == ("extract", "m1", "u1", 0.5, 7)


def test_llm_call_without_vendor_cost_is_unpriced_not_guessed(events):
    with usage_scope("extract", memo_id="m1"):
        record_llm_usage("vertex_ai", {"prompt_tokens": 7})
    assert events[0].cost_usd is None


def test_nested_scopes_inherit(events):
    with usage_scope("capture", user_id="u1", capture_id="cap"):
        with usage_scope("sanitize", memo_id="m1"):
            record_llm_usage("openrouter", {})
    e = events[0]
    assert (e.purpose, e.user_id, e.capture_id, e.memo_id) == ("sanitize", "u1", "cap", "m1")


@pytest.mark.asyncio
async def test_scoped_decorator_reads_ids_from_arguments(events):
    @scoped("followup")
    async def run(supabase, memo_id, *, llm=None):
        record_llm_usage("openrouter", {})

    await run(object(), "m9")
    await flush()
    assert (events[0].purpose, events[0].memo_id) == ("followup", "m9")


def test_stt_cost_matches_the_list_price_per_tier():
    assert stt_cost_usd("speechmatics", "realtime", 3600, tier="enhanced") == 0.43
    assert stt_cost_usd("speechmatics", "batch", 3600, tier="standard") == 0.24


def test_stt_with_no_rate_keeps_seconds_but_no_price(events):
    with usage_scope("stt_batch", memo_id="m1"):
        record_stt_usage("deepgram", "batch", 120)
    assert (events[0].cost_usd, events[0].audio_seconds) == (None, 120)


def test_live_stt_is_priced_and_keyed_by_capture(events):
    with usage_scope("live_stt", user_id="u1", capture_id="cap-1"):
        record_stt_usage("speechmatics", "realtime", 1800, channels=2, tier="enhanced")
    e = events[0]
    assert (e.cost_usd, e.capture_id, e.memo_id) == (0.215, "cap-1", None)


def test_per_channel_billing_is_opt_in():
    with patch("app.services.usage.pricing.settings") as cfg:
        cfg.STT_BILL_PER_CHANNEL = True
        cfg.STT_RATE_SPEECHMATICS_REALTIME_ENHANCED_USD_HR = 0.43
        assert stt_cost_usd("speechmatics", "realtime", 3600, channels=2, tier="enhanced") == 0.86


def test_event_without_memo_or_capture_is_only_logged(events):
    record_llm_usage("openrouter", {"cost_usd": 1})
    assert events == []


def test_disabled_ledger_writes_nothing(events):
    with patch("app.services.usage.ledger.settings") as cfg:
        cfg.USAGE_LEDGER_ENABLED = False
        with usage_scope("extract", memo_id="m1"):
            record_llm_usage("openrouter", {})
    assert events == []


def test_write_resolves_the_memo_from_the_capture_and_calls_the_rpc():
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"id": "m7"}
    ]
    event = ledger.UsageEvent("live_stt", user_id="u1", capture_id="cap-1", cost_usd=0.59, audio_seconds=4958)
    with patch("app.deps.get_supabase", return_value=sb):
        _REAL_WRITE(event)
    name, args = sb.rpc.call_args.args
    assert name == "add_memo_cost"
    assert (args["p_memo"], args["p_purpose"], args["p_usd"], args["p_audio_seconds"]) == ("m7", "live_stt", 0.59, 4958)


def test_write_failure_never_raises():
    event = ledger.UsageEvent("extract", memo_id="m1", cost_usd=1)
    with patch("app.deps.get_supabase", side_effect=RuntimeError("db down")):
        _REAL_WRITE(event)


def test_write_without_a_memo_calls_nothing():
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    with patch("app.deps.get_supabase", return_value=sb):
        _REAL_WRITE(ledger.UsageEvent("live_stt", user_id="u1", capture_id="unknown"))
    sb.rpc.assert_not_called()


def test_memo_report_reads_the_memo_columns():
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {
            "id": "m1",
            "cost_usd": "0.68",
            "cost_breakdown": {
                "live_stt": {"usd": 0.59, "unpriced": 0},
                "sanitize": {"usd": 0.09, "unpriced": 1},
            },
        }
    ]
    report = memo_cost_report(sb, "m1")
    assert report["total_cost_usd"] == 0.68
    assert report["unpriced_events"] == 1


def test_period_summary_adds_steps_across_memos():
    sb = MagicMock()
    page = sb.table.return_value.select.return_value.gte.return_value.gt.return_value.order.return_value.range.return_value
    page.execute.return_value.data = [
        {"cost_usd": 0.6, "cost_breakdown": {"live_stt": {"usd": 0.5, "events": 1}, "extract": {"usd": 0.1, "events": 1}}},
        {"cost_usd": 0.2, "cost_breakdown": {"extract": {"usd": 0.2, "events": 2}}},
    ]
    out = period_summary(sb, 7)
    assert out["total_cost_usd"] == 0.8
    assert out["avg_cost_per_memo_usd"] == 0.4
    assert out["by_purpose"]["extract"]["usd"] == 0.3
    assert out["by_purpose"]["extract"]["events"] == 3


@respx.mock
@pytest.mark.asyncio
async def test_openrouter_call_asks_for_cost_and_records_it(events):
    route = respx.post(OPENROUTER_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "hi"}}],
                "model": "google/gemini-3.5-flash-lite",
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "cost": 0.004},
            },
        )
    )
    with usage_scope("ask", user_id="u1", memo_id="m1"):
        await OpenRouterProvider(api_key="k", model="m").chat([{"role": "user", "content": "x"}])
    await flush()
    assert b'"include":true' in route.calls[0].request.content.replace(b" ", b"")
    assert (events[0].cost_usd, events[0].purpose) == (0.004, "ask")
