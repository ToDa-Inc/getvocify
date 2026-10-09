"""HubSpot analytics: exact counts from search totals, honest about what HubSpot cannot tell."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services.crm_copilot import crm_analytics as ca
from app.services.hubspot.call_log import HUBSPOT_DISPOSITION_GUID as G
from app.services.hubspot.exceptions import HubSpotError
from app.services.hubspot.types import CRMSchema, HubSpotProperty, PropertyOption
from tests.crm_copilot.fakes import FakeHubSpotClient

START = datetime(2026, 8, 1, tzinfo=timezone.utc)
END = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _ms(day):
    return str(int(datetime(2026, 8, day, 12, tzinfo=timezone.utc).timestamp() * 1000))


def _call(day, outcome=None, owner="1", direction="OUTBOUND"):
    props = {"hs_timestamp": _ms(day), "hubspot_owner_id": owner, "hs_call_direction": direction}
    if outcome:
        props["hs_call_disposition"] = G[outcome]
    return props


CALLS = (
    [_call(3, "connected")] * 3
    + [_call(4, "no_answer")] * 4
    + [_call(5, "voicemail")] * 2
    + [_call(6, "busy")]
    + [_call(7, "connected", owner="2")]
    + [_call(8, direction="INBOUND", outcome="connected")]
    + [{"hs_timestamp": str(int(datetime(2026, 7, 20, tzinfo=timezone.utc).timestamp() * 1000)), "hs_call_direction": "OUTBOUND", "hs_call_disposition": G["connected"], "hubspot_owner_id": "1"}]
)


@pytest.mark.asyncio
async def test_the_connection_rate_of_a_month_counts_only_outbound_calls_in_that_month():
    stats = await ca.call_stats(FakeHubSpotClient(calls=CALLS), start=START, end=END)
    assert stats["total"] == 11  # 3+4+2+1+1 outbound in August; the inbound and July calls are out
    assert stats["connected"] == 4
    assert stats["no_answer"] == 4 and stats["voicemail"] == 2 and stats["busy"] == 1
    assert stats["connection_rate_pct"] == pytest.approx(36.4, abs=0.05)
    assert stats["outcome_unknown"] == 0


@pytest.mark.asyncio
async def test_calls_without_a_logged_outcome_are_reported_not_counted_as_not_connected():
    calls = [_call(3, "connected")] * 2 + [_call(4)] * 6  # six calls with no disposition
    stats = await ca.call_stats(FakeHubSpotClient(calls=calls), start=START, end=END)
    assert stats["total"] == 8 and stats["outcome_unknown"] == 6
    assert stats["outcome_known_pct"] == 25.0


@pytest.mark.asyncio
async def test_one_rep_is_filtered_by_owner_id():
    stats = await ca.call_stats(FakeHubSpotClient(calls=CALLS), start=START, end=END, owner_id="2")
    assert stats["total"] == 1 and stats["connected"] == 1


@pytest.mark.asyncio
async def test_direction_all_includes_inbound():
    stats = await ca.call_stats(FakeHubSpotClient(calls=CALLS), start=START, end=END, direction=None)
    assert stats["total"] == 12


@pytest.mark.asyncio
async def test_requests_are_exact_count_searches_not_full_downloads():
    client = FakeHubSpotClient(calls=CALLS)
    await ca.call_stats(client, start=START, end=END)
    assert client.requests, "no request made"
    assert all(payload.get("limit") == 1 for _, payload in client.requests)
    assert len(client.requests) <= 6


@pytest.mark.asyncio
async def test_by_owner_names_reps_and_skips_reps_with_no_calls():
    owners = [
        {"id": "1", "firstName": "Ana", "lastName": "Ruiz", "email": "ana@x.test"},
        {"id": "2", "firstName": "Luis", "lastName": "", "email": "luis@x.test"},
        {"id": "3", "firstName": "Zoe", "lastName": "", "email": "zoe@x.test"},
    ]
    rows = await ca.call_stats_by_owner(FakeHubSpotClient(calls=CALLS, owners=owners), start=START, end=END)
    assert [r["rep"] for r in rows] == ["Ana Ruiz", "Luis"]  # alphabetical, Zoe had no calls
    assert rows[0]["total"] == 10 and rows[0]["connected"] == 3
    assert rows[1]["total"] == 1


def _schema(prop="closed_lost_reason"):
    return CRMSchema(
        object_type="deals",
        properties=[
            HubSpotProperty(
                name=prop, label="Closed lost reason", type="enumeration", fieldType="select",
                options=[PropertyOption(label="Precio", value="price"), PropertyOption(label="Sin presupuesto", value="no_budget"), PropertyOption(label="Competidor", value="competitor")],
            )
        ],
    )


def _schema_service(schema):
    async def get_deal_schema(use_cache=True):
        return schema

    return SimpleNamespace(get_deal_schema=get_deal_schema)


def _deal(day, won=False, lost=False, reason=None, owner="1"):
    props = {"closedate": _ms(day), "hs_is_closed_won": "true" if won else "false", "hs_is_closed_lost": "true" if lost else "false", "hubspot_owner_id": owner, "amount": "1000"}
    if reason:
        props["closed_lost_reason"] = reason
    return props


DEALS = (
    [_deal(3, lost=True, reason="price")] * 4
    + [_deal(4, lost=True, reason="no_budget")] * 2
    + [_deal(5, lost=True, reason="competitor")]
    + [_deal(6, lost=True)] * 3
    + [_deal(7, won=True)] * 5
)


@pytest.mark.asyncio
async def test_top_lost_reasons_use_labels_and_report_deals_with_no_reason():
    out = await ca.lost_reasons(FakeHubSpotClient(deals=DEALS), _schema_service(_schema()), start=START, end=END, top_n=2)
    assert out["lost"] == 10 and out["won"] == 5
    assert out["win_rate_pct"] == pytest.approx(33.3, abs=0.05)
    assert [(r["reason"], r["count"]) for r in out["reasons"]] == [("Precio", 4), ("Sin presupuesto", 2)]
    assert out["reasons"][0]["share_pct"] == 40.0
    assert out["no_reason"] == 3
    assert out["reason_property"] == "Closed lost reason"
    assert out["fetched"] == 10


@pytest.mark.asyncio
async def test_when_no_lost_reason_property_exists_counts_are_given_but_reasons_are_not_invented():
    schema = CRMSchema(object_type="deals", properties=[HubSpotProperty(name="dealname", label="Deal name", type="string")])
    out = await ca.lost_reasons(FakeHubSpotClient(deals=DEALS), _schema_service(schema), start=START, end=END, top_n=5)
    assert out["lost"] == 10 and out["reasons"] is None and out["reason_property"] is None


@pytest.mark.asyncio
async def test_more_lost_deals_than_fetched_is_reported_as_a_partial_read():
    many = [_deal(3, lost=True, reason="price")] * 30
    out = await ca.lost_reasons(FakeHubSpotClient(deals=many), _schema_service(_schema()), start=START, end=END, top_n=5, max_fetch=10)
    assert out["lost"] == 30 and out["fetched"] == 10


@pytest.mark.asyncio
async def test_a_hubspot_error_surfaces_instead_of_returning_zeros():
    client = FakeHubSpotClient(fail_with=HubSpotError("403 forbidden: missing scope"))
    with pytest.raises(HubSpotError):
        await ca.call_stats(client, start=START, end=END)


def test_month_and_date_arguments_resolve_in_the_actors_timezone():
    start, end = ca.resolve_period({"month": "2026-08"}, "Europe/Madrid")
    assert start.isoformat() == "2026-07-31T22:00:00+00:00" and end.isoformat() == "2026-08-31T22:00:00+00:00"
    start, end = ca.resolve_period({"start_date": "2026-08-10", "end_date": "2026-08-12"}, "Europe/Madrid")
    assert (end - start).days == 3  # inclusive end date
    with pytest.raises(ValueError):
        ca.resolve_period({"start_date": "2024-01-01", "end_date": "2026-09-01"}, "UTC")
    with pytest.raises(ValueError):
        ca.resolve_period({"month": "agosto"}, "UTC")
    with pytest.raises(ValueError):
        ca.resolve_period({}, "UTC")


def test_a_rolling_window_of_days_ends_now_and_is_bounded():
    start, end = ca.resolve_period({"period_days": 7}, "UTC")
    assert 6.99 < (end - start).total_seconds() / 86400 < 7.01
    with pytest.raises(ValueError):
        ca.resolve_period({"period_days": 4000}, "UTC")
