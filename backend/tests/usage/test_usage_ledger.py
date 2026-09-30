from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from app.services.llm.providers.openrouter import OPENROUTER_URL, OpenRouterProvider, openrouter_call_meta
from app.services.usage import flush, record_llm_usage, record_stt_usage, scoped, usage_scope
from app.services.usage.pricing import stt_cost_usd
from app.services.usage.report import memo_cost_report, summarize


@pytest.fixture
def rows():
    """Capture what the ledger would insert, without a database."""
    captured: list[dict] = []
    with patch("app.services.usage.ledger._insert", side_effect=captured.append):
        yield captured


def test_openrouter_meta_carries_billed_cost_and_token_details():
    meta = openrouter_call_meta(
        {
            "model": "google/gemini-3.5-flash-lite",
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "cost": 0.0123,
                "completion_tokens_details": {"reasoning_tokens": 3},
                "prompt_tokens_details": {"cached_tokens": 4},
            },
        },
        requested_model="x",
    )
    assert meta["cost_usd"] == 0.0123
    assert meta["reasoning_tokens"] == 3
    assert meta["cached_tokens"] == 4


def test_llm_event_uses_provider_cost_and_the_current_scope(rows):
    with usage_scope("extract", user_id="u1", memo_id="m1") as scope:
        record_llm_usage("openrouter", {"model": "m", "prompt_tokens": 7, "cost_usd": 0.5})
    assert rows[0]["cost_source"] == "provider_reported"
    assert rows[0]["cost_usd"] == 0.5
    assert (rows[0]["purpose"], rows[0]["user_id"], rows[0]["memo_id"]) == ("extract", "u1", "m1")
    assert rows[0]["scope_id"] == scope.scope_id


def test_llm_event_without_cost_is_unpriced_not_guessed(rows):
    record_llm_usage("vertex_ai", {"model": "g", "prompt_tokens": 7})
    assert rows[0]["cost_source"] == "unpriced"
    assert "cost_usd" not in rows[0]


def test_nested_scopes_inherit_and_keep_one_scope_id(rows):
    with usage_scope("capture", user_id="u1", capture_id="cap") as outer:
        with usage_scope("sanitize", memo_id="m1") as inner:
            record_llm_usage("openrouter", {"model": "m"})
    assert inner.scope_id == outer.scope_id
    assert (rows[0]["purpose"], rows[0]["user_id"], rows[0]["capture_id"], rows[0]["memo_id"]) == (
        "sanitize",
        "u1",
        "cap",
        "m1",
    )


@pytest.mark.asyncio
async def test_scoped_decorator_reads_ids_from_arguments(rows):
    @scoped("followup")
    async def run(supabase, memo_id, *, llm=None):
        record_llm_usage("openrouter", {"model": "m"})

    await run(object(), "m9")
    await flush()
    assert (rows[0]["purpose"], rows[0]["memo_id"]) == ("followup", "m9")


def test_stt_cost_matches_the_list_price_per_tier():
    assert stt_cost_usd("speechmatics", "realtime", 3600, tier="enhanced") == 0.43
    assert stt_cost_usd("speechmatics", "batch", 3600, tier="standard") == 0.24


def test_stt_with_no_rate_is_unpriced(rows):
    record_stt_usage("deepgram", "batch", 120, model="nova-3")
    assert rows[0]["cost_source"] == "unpriced"
    assert rows[0]["audio_seconds"] == 120


def test_stt_event_records_computed_cost_and_channels(rows):
    with usage_scope("live_stt", user_id="u1"):
        record_stt_usage("speechmatics", "realtime", 1800, channels=2, model="enhanced")
    assert rows[0]["cost_usd"] == 0.215
    assert rows[0]["cost_source"] == "computed"
    assert rows[0]["channels"] == 2


def test_per_channel_billing_is_opt_in():
    with patch("app.services.usage.pricing.settings") as cfg:
        cfg.STT_BILL_PER_CHANNEL = True
        cfg.STT_RATE_SPEECHMATICS_REALTIME_ENHANCED_USD_HR = 0.43
        assert stt_cost_usd("speechmatics", "realtime", 3600, channels=2, tier="enhanced") == 0.86


def test_ledger_failure_never_raises():
    with patch("app.deps.get_supabase", side_effect=RuntimeError("db down")):
        record_llm_usage("openrouter", {"model": "m", "cost_usd": 1})  # must not raise


def test_disabled_ledger_writes_nothing(rows):
    with patch("app.services.usage.ledger.settings") as cfg:
        cfg.USAGE_LEDGER_ENABLED = False
        record_llm_usage("openrouter", {"model": "m"})
    assert rows == []


def test_summary_counts_unpriced_separately():
    events = [
        {"purpose": "extract", "cost_usd": 0.1, "prompt_tokens": 5},
        {"purpose": "extract", "cost_usd": None},
        {"purpose": "sanitize", "cost_usd": 0.3},
    ]
    groups = summarize(events, "purpose")
    assert [g["purpose"] for g in groups] == ["sanitize", "extract"]
    assert groups[1]["unpriced_events"] == 1
    assert groups[1]["cost_usd"] == 0.1


def test_memo_report_follows_the_desktop_capture():
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"id": "m1", "client_capture_id": "cap-1"}
    ]
    events_q = sb.table.return_value.select.return_value.or_.return_value.order.return_value.execute
    events_q.return_value.data = [
        {"kind": "stt", "purpose": "live_stt", "cost_usd": 0.59},
        {"kind": "llm", "purpose": "sanitize", "cost_usd": 0.09},
    ]
    report = memo_cost_report(sb, "m1")
    sb.table.return_value.select.return_value.or_.assert_called_once_with("memo_id.eq.m1,capture_id.eq.cap-1")
    assert report["total_cost_usd"] == 0.68


@respx.mock
@pytest.mark.asyncio
async def test_openrouter_call_asks_for_cost_and_records_it(rows):
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
    with usage_scope("ask", user_id="u1"):
        await OpenRouterProvider(api_key="k", model="m").chat([{"role": "user", "content": "x"}])
    await flush()
    assert b'"include":true' in route.calls[0].request.content.replace(b" ", b"")
    assert rows[0]["cost_usd"] == 0.004
    assert rows[0]["purpose"] == "ask"
