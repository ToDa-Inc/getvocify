"""T6: the AE deals section's pure pieces - merging handoff/own candidates and reading
CRM deal stages best-effort."""

from __future__ import annotations

from app.services.hoy.deals import (
    HUBSPOT_BATCH_LIMIT,
    deal_reason,
    deal_stages_by_provider,
    merge_deal_candidates,
    newest_first,
    own_deal_candidates,
    stage_known_ended,
)


def test_own_deal_candidates_keeps_the_newest_memo_per_deal():
    memos = [
        {"id": "m1", "hubspot_deal_id": "d1", "hubspot_contact_id": "c1", "connection_id": "crm-A", "created_at": "2026-09-20T10:00:00Z"},
        {"id": "m2", "hubspot_deal_id": "d1", "hubspot_contact_id": "c1", "connection_id": "crm-A", "created_at": "2026-09-25T10:00:00Z"},
        {"id": "m3", "hubspot_deal_id": None, "hubspot_contact_id": "c2", "created_at": "2026-09-26T10:00:00Z"},
    ]
    out = own_deal_candidates(memos)
    assert len(out) == 1
    assert out[0]["deal_id"] == "d1"
    assert out[0]["memo_id"] == "m2"


def test_merge_prefers_the_handoff_over_the_ae_own_capture_of_the_same_deal():
    handoffs = [{"deal_id": "d1", "contact_id": "c1", "connection_id": "crm-A", "sdr_user_id": "sdr-1"}]
    own = [{"deal_id": "d1", "contact_id": "c1", "connection_id": "crm-A"}, {"deal_id": "d2", "contact_id": "c2"}]
    merged = merge_deal_candidates(handoffs, own)
    assert [row["deal_id"] for row in merged] == ["d1", "d2"]
    assert merged[0]["source"] == "handoff"
    assert merged[0]["sdr_user_id"] == "sdr-1"
    assert merged[1]["source"] == "own"


def test_merge_dedupes_by_contact_when_no_deal_id():
    handoffs = [{"deal_id": None, "contact_id": "c1", "sdr_user_id": "sdr-1"}]
    own = [{"deal_id": None, "contact_id": "c1"}]
    assert len(merge_deal_candidates(handoffs, own)) == 1


def test_deal_reason_falls_back_to_own_for_an_unknown_source():
    assert deal_reason("handoff", lang="es") == "Traspasado a ti"
    assert deal_reason("own", lang="en") == "Deal in progress"
    assert deal_reason("mystery") == "Deal en curso"


def test_hubspot_stage_batch_read():
    def fetch(request):
        assert request["path"] == "/crm/v3/objects/deals/batch/read"
        return {"results": [{"id": "d1", "properties": {"dealstage": "closedwon"}}]}

    stages = deal_stages_by_provider(fetch, "hubspot", ["d1"])
    # hs_is_closed absent in the response: not closed by that signal (closedwon still ends it).
    assert stages == {"d1": {"stage_id": "closedwon", "is_closed": False}}


def test_pipedrive_stage_reads_one_deal_at_a_time():
    calls = []

    def fetch(request):
        calls.append(request["path"])
        return {"data": {"status": "won"}}

    stages = deal_stages_by_provider(fetch, "pipedrive", ["9", "10"])
    assert calls == ["/deals/9", "/deals/10"]
    assert stages == {"9": {"status": "won"}, "10": {"status": "won"}}


def test_a_failed_read_yields_no_stage_for_that_deal():
    def fetch(_request):
        return {"error_kind": "unavailable"}

    assert deal_stages_by_provider(fetch, "hubspot", ["d1"]) == {}


def test_deal_stages_by_provider_swallows_a_transport_error():
    def fetch(_request):
        raise TimeoutError("boom")

    assert deal_stages_by_provider(fetch, "pipedrive", ["9"]) == {}


def test_hubspot_stage_reads_are_chunked_to_the_batch_limit():
    calls = []

    def fetch(request):
        ids = [row["id"] for row in request["json"]["inputs"]]
        calls.append(ids)
        return {"results": [{"id": deal_id, "properties": {"dealstage": "open"}} for deal_id in ids]}

    ids = [str(i) for i in range(HUBSPOT_BATCH_LIMIT + 50)]
    stages = deal_stages_by_provider(fetch, "hubspot", ids)
    assert len(calls) == 2
    assert len(calls[0]) == HUBSPOT_BATCH_LIMIT
    assert len(calls[1]) == 50
    assert len(stages) == len(ids)


def test_newest_first_sorts_by_created_at_descending_and_caps_at_limit():
    rows = [
        {"deal_id": "old", "created_at": "2026-09-01T10:00:00Z"},
        {"deal_id": "new", "created_at": "2026-09-20T10:00:00Z"},
        {"deal_id": "missing"},
    ]
    assert [row["deal_id"] for row in newest_first(rows, limit=2)] == ["new", "old"]


def test_stage_known_ended_needs_an_actual_read_never_guesses():
    assert stage_known_ended({}, "d1", provider="hubspot") is False
    assert stage_known_ended({"d1": {"stage_id": "closedwon"}}, "d1", provider="hubspot") is True
    assert stage_known_ended({"d1": {"stage_id": "appointmentscheduled"}}, "d1", provider="hubspot") is False
    assert stage_known_ended({"9": {"status": "won"}}, "9", provider="pipedrive") is True
    assert stage_known_ended({}, None, provider="hubspot") is False
