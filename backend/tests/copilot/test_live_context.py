"""What live help reads before each card is kept for a short time: only successful reads, keyed by everything the value
depends on, cleared when a playbook changes, and never able to make a card wrong."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-copilot-32-chars")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-copilot-32-chars")

import asyncio
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import copilot as copilot_api
from app.config import settings
from app.deps import get_membership, get_supabase, get_user_id
from app.services import extraction_context
from app.services.company import Membership
from app.services.copilot import events, live_context, playbook_objections
from app.services.copilot.grounding import SuggestGrounding
from app.services.llm.jev import JevClient


def run(coro):
    return asyncio.run(coro)


class Counter:
    """A loader that counts its reads and can fail on chosen ones."""

    def __init__(self, value="v", fail_on=()):
        self.value, self.fail_on, self.calls = value, set(fail_on), 0

    def __call__(self, *_a, **_k):
        self.calls += 1
        if self.calls in self.fail_on:
            raise RuntimeError("database down")
        return self.value


# --- The cache itself --------------------------------------------------------------------------------------------


def test_the_second_read_of_a_key_comes_from_the_cache():
    loader = Counter("offer")
    first = run(live_context.cached(("product", "u1"), loader))
    second = run(live_context.cached(("product", "u1"), loader))
    assert (first.value, first.hit, second.value, second.hit) == ("offer", False, "offer", True)
    assert loader.calls == 1


def test_a_value_expires_after_the_ttl(monkeypatch):
    monkeypatch.setattr(settings, "COPILOT_CONTEXT_TTL_S", 0.05)
    loader = Counter()
    run(live_context.cached(("k",), loader))
    time.sleep(0.08)
    assert run(live_context.cached(("k",), loader)).hit is False
    assert loader.calls == 2


def test_a_ttl_of_zero_reads_every_time_as_before(monkeypatch):
    monkeypatch.setattr(settings, "COPILOT_CONTEXT_TTL_S", 0)
    loader = Counter()
    reads = [run(live_context.cached(("k",), loader)) for _ in range(3)]
    assert loader.calls == 3 and not any(read.hit for read in reads)
    assert live_context.cache_state(reads) == "off"


def test_a_failed_read_gives_the_fallback_and_is_never_kept():
    loader = Counter("good", fail_on={1})
    failed = run(live_context.cached(("knowledge", "c1"), loader, fallback="nothing"))
    assert (failed.value, failed.failed, failed.hit) == ("nothing", True, False)
    # The next card reads again, and only that success is kept.
    ok = run(live_context.cached(("knowledge", "c1"), loader, fallback="nothing"))
    again = run(live_context.cached(("knowledge", "c1"), loader, fallback="nothing"))
    assert (ok.value, ok.hit, again.value, again.hit) == ("good", False, "good", True)
    assert loader.calls == 2


def test_no_playbook_is_a_result_worth_keeping_but_an_error_is_not():
    none_loader = Counter(None)
    run(live_context.cached(("grounding", "c1", "discovery"), none_loader))
    assert run(live_context.cached(("grounding", "c1", "discovery"), none_loader)).hit is True
    assert none_loader.calls == 1


def test_the_cache_is_bounded_and_drops_the_oldest(monkeypatch):
    small = live_context.TtlCache(max_entries=3)
    for n in range(5):
        small.put(("k", n), n)
        time.sleep(0.002)
    assert len(small) == 3
    assert small.get(("k", 0), 60) is live_context._MISSING and small.get(("k", 4), 60) == 4


def test_a_playbook_change_clears_only_that_companys_playbooks():
    for key in (("grounding", "c1", "discovery"), ("grounding", "c1", "closing"), ("grounding", "c2", "discovery"), ("knowledge", "c1")):
        live_context._cache.put(key, "x")
    assert live_context.invalidate_company("c1") == 2
    assert live_context._cache.get(("grounding", "c2", "discovery"), 60) == "x"
    assert live_context._cache.get(("knowledge", "c1"), 60) == "x"
    assert live_context.invalidate_company(None) == 0


# --- /copilot/suggest and /copilot/turn ---------------------------------------------------------------------------


def grounding(version="v-disc", kind="call"):
    return SuggestGrounding(kind, version, frozenset(), {"version_id": version, "entries": []})


class Server:
    """The suggest route with every database read replaced by a counter, and the model by a recorder."""

    def __init__(self, monkeypatch):
        self.product, self.knowledge, self.tz = Counter("offer"), Counter({"value_short": "x"}), Counter("Europe/Madrid")
        self.by_type = {"discovery": grounding("v-disc"), "negotiation": grounding("v-neg")}
        self.grounding_calls: list[str] = []
        self.grounding_fail = False
        self.routed, self.capture = Counter(None), Counter(None)
        self.streams: list[dict] = []
        self.rows: list[dict] = []
        server = self

        def grounding_for_type(_db, _company, key, kind, **_k):
            server.grounding_calls.append(key)
            if server.grounding_fail:
                raise RuntimeError("database down")
            return grounding(server.by_type[key].playbook_version_id, kind)

        async def fake_stream(**kwargs):
            server.streams.append(kwargs)
            yield {"type": "result", "model": "m", "latency_ms": 5, "suggestion": {"is_objection": False, "say_this": ""}}

        monkeypatch.setattr(extraction_context, "load_product_context", self.product)
        monkeypatch.setattr(copilot_api, "load_company_knowledge", self.knowledge)
        monkeypatch.setattr(copilot_api, "rep_timezone", self.tz)
        monkeypatch.setattr(copilot_api.call_type, "grounding_for_type", grounding_for_type)
        monkeypatch.setattr(copilot_api, "load_company_suggest_grounding", self.routed)
        monkeypatch.setattr(copilot_api, "load_suggest_grounding", self.capture)
        monkeypatch.setattr(copilot_api, "stream_objection_suggestion", fake_stream)
        monkeypatch.setattr(events, "record", lambda _db, row: row and server.rows.append(row))

        app = FastAPI()
        app.include_router(copilot_api.router)
        app.dependency_overrides[get_supabase] = lambda: object()
        app.dependency_overrides[get_user_id] = lambda: "user-1"
        app.dependency_overrides[get_membership] = lambda: Membership(
            id="m", company_id="co-1", user_id="user-1", role="member", status="active",
        )
        self.client = TestClient(app)

    def suggest(self, **extra):
        body = {"transcript_window": "Them: caro", "latest_turn": "caro", "call_mode": "softphone",
                "speaker_role": "prospect", "sales_motion_key": "discovery", **extra}
        response = self.client.post("/api/v1/copilot/suggest", json=body)
        assert response.status_code == 200
        return self.streams[-1]

    def loads(self):
        return (self.product.calls, self.knowledge.calls, len(self.grounding_calls), self.tz.calls)


@pytest.fixture
def server(monkeypatch):
    return Server(monkeypatch)


def test_the_second_card_reads_nothing_from_the_database(server):
    server.suggest()
    assert server.loads() == (1, 1, 1, 1)
    second = server.suggest()
    assert server.loads() == (1, 1, 1, 1)
    assert second["product_context"] == "offer" and second["company_knowledge"] == {"value_short": "x"}
    assert second["grounding"].playbook_version_id == "v-disc"
    assert [row["client"]["cache"] for row in server.rows] == ["cold", "hit"]
    assert all(isinstance(row["client"]["prep_ms"], int) for row in server.rows)


def test_a_type_changed_mid_call_reads_that_types_playbook_and_keeps_it_apart(server):
    assert server.suggest()["grounding"].playbook_version_id == "v-disc"
    assert server.suggest(sales_motion_key="negotiation")["grounding"].playbook_version_id == "v-neg"
    assert server.suggest(sales_motion_key="discovery")["grounding"].playbook_version_id == "v-disc"
    assert server.suggest(sales_motion_key="negotiation")["grounding"].playbook_version_id == "v-neg"
    assert server.grounding_calls == ["discovery", "negotiation"]
    # What does not depend on the type was read once.
    assert (server.product.calls, server.knowledge.calls, server.tz.calls) == (1, 1, 1)


def test_the_playbook_is_shared_but_each_card_has_its_own_channel(server):
    assert server.suggest(call_mode="softphone")["grounding"].interaction_kind == "call"
    assert server.suggest(call_mode="meeting")["grounding"].interaction_kind == "meeting"
    assert len(server.grounding_calls) == 1


def test_a_failed_playbook_read_gives_general_help_once_and_is_read_again(server):
    server.grounding_fail = True
    assert server.suggest()["grounding"] is None
    server.grounding_fail = False
    assert server.suggest()["grounding"].playbook_version_id == "v-disc"
    assert server.suggest()["grounding"].playbook_version_id == "v-disc"
    assert server.grounding_calls == ["discovery", "discovery"]


def test_a_read_that_fails_does_not_stop_the_others(server):
    server.knowledge.fail_on = {1}
    first = server.suggest()
    assert first["company_knowledge"] is None and first["product_context"] == "offer"
    assert server.suggest()["company_knowledge"] == {"value_short": "x"}


def test_a_capture_and_a_call_without_a_type_are_read_every_time(server):
    server.suggest(capture_id="cap-1")
    server.suggest(capture_id="cap-1")
    assert server.capture.calls == 2 and server.grounding_calls == []
    server.suggest(sales_motion_key=None)
    server.suggest(sales_motion_key=None)
    assert server.routed.calls == 2


def test_an_offer_sent_with_the_request_is_used_and_not_read(server):
    stream = server.suggest(product_context="Nuestra oferta")
    assert stream["product_context"] == "Nuestra oferta" and server.product.calls == 0


def test_an_internal_call_reads_nothing_and_calls_no_model(server):
    server.client.post("/api/v1/copilot/suggest", json={
        "transcript_window": "x", "latest_turn": "y", "sales_motion_key": "internal",
    })
    assert server.loads() == (0, 0, 0, 0) and server.streams == []


def test_with_the_cache_off_every_card_reads_as_before(server, monkeypatch):
    monkeypatch.setattr(settings, "COPILOT_CONTEXT_TTL_S", 0)
    server.suggest()
    server.suggest()
    assert server.loads() == (2, 2, 2, 2)
    assert [row["client"]["cache"] for row in server.rows] == ["off", "off"]


def test_a_playbook_change_is_live_on_the_next_card(server):
    from app.api import playbooks as playbooks_api

    server.suggest()
    playbooks_api._playbooks_changed("co-1")
    server.suggest()
    assert server.grounding_calls == ["discovery", "discovery"]
    # Another company's change leaves it alone.
    playbooks_api._playbooks_changed("co-other")
    server.suggest()
    assert server.grounding_calls == ["discovery", "discovery"]


def test_a_publish_or_a_pause_clears_what_live_help_kept():
    import inspect

    from app.api import playbooks as playbooks_api

    # The only two routes that change what applies to a call go through the same clearing.
    assert "_playbooks_changed(membership.company_id)" in inspect.getsource(playbooks_api.publish_motion)
    assert "_playbooks_changed(membership.company_id)" in inspect.getsource(playbooks_api._lifecycle)


def test_a_changed_playbook_reaches_the_turn_checks_custom_objections_too():
    playbook_objections._company["user-1"] = "co-1"
    playbook_objections._company["user-2"] = "co-2"
    playbook_objections._cache[("user-1", "discovery")] = (time.monotonic(), {"x": {}})
    playbook_objections._cache[("user-2", "discovery")] = (time.monotonic(), {"y": {}})
    playbook_objections.invalidate_company("co-1")
    assert ("user-1", "discovery") not in playbook_objections._cache
    assert ("user-2", "discovery") in playbook_objections._cache


def _turn(client, text="me parece caro"):
    return client.post("/api/v1/copilot/turn", json={
        "transcript_window": f"Them: {text}", "latest_turn": text, "sales_motion_key": "discovery",
    })


def test_the_turn_check_has_the_cards_context_ready(server, monkeypatch):
    async def fake_post(self, state, questions):
        return {"turn": {"choice": "finished", "confidence": 0.9}, "objection": {"choice": "price", "confidence": 1}}

    monkeypatch.setattr(JevClient, "_post_systemone", fake_post)
    monkeypatch.setattr(JevClient, "is_available", property(lambda self: True))
    monkeypatch.setattr(playbook_objections, "custom_for", lambda *_a: {})
    playbook_objections._company["user-1"] = "co-1"
    assert _turn(server.client).status_code == 200
    # Read after the response, so the card that follows finds all of it.
    assert server.loads() == (1, 1, 1, 1)
    server.suggest()
    assert server.loads() == (1, 1, 1, 1)
    assert [row["client"]["cache"] for row in server.rows if row["kind"] == "suggest"] == ["hit"]


def test_a_turn_check_before_the_company_is_known_warms_nothing_and_never_fails(server, monkeypatch):
    async def fake_post(self, state, questions):
        return {"turn": {"choice": "finished", "confidence": 0.9}, "objection": {"choice": "none", "confidence": 1}}

    monkeypatch.setattr(JevClient, "_post_systemone", fake_post)
    monkeypatch.setattr(JevClient, "is_available", property(lambda self: True))
    monkeypatch.setattr(playbook_objections, "custom_for", lambda *_a: {})
    assert _turn(server.client).status_code == 200
    assert server.loads() == (0, 0, 0, 0)


def test_warming_never_raises_even_when_every_read_fails(server):
    for loader in (server.product, server.knowledge, server.tz):
        loader.fail_on = set(range(1, 10))
    server.grounding_fail = True
    playbook_objections._company["user-1"] = "co-1"
    run(copilot_api._warm_context(object(), "user-1", "discovery"))
    assert live_context.ttl_s() > 0
