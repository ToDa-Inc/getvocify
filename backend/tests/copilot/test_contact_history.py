"""Live suggestions know what earlier calls with the same contact left behind."""

import os
from types import SimpleNamespace

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-copilot-32-chars")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-copilot-32-chars")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import copilot as copilot_api
from app.deps import get_membership, get_supabase
from app.services.company import Membership
from app.services.copilot import contact_history as history_mod
from app.services.copilot.contact_history import format_contact_history, load_contact_history
from app.services.copilot.prompts import build_user_prompt
from app.services.playbooks.catalog import INTERNAL_KEY


def _memo(day, *, summary=None, objections=(), commitments=(), competitors=(), interest=None, **extra):
    return {
        "id": f"m-{day}",
        "created_at": f"{day}T10:00:00+00:00",
        "user_id": "rep-1",
        "extraction": {
            "summary": summary,
            "intelligence": {
                "interest": interest,
                "objections": list(objections),
                "commitments": list(commitments),
                "competitor_mentions": [{"name": c} for c in competitors],
            },
        },
        **extra,
    }


PRICE = {
    "category": "price",
    "resolution": "unresolved",
    "quote": "Es demasiado caro para nosotros ahora mismo",
    "response": {"text": "Lo vemos con el ROI del primer trimestre"},
}


def test_formats_latest_summary_objections_commitments_and_competitors():
    text = format_contact_history([
        _memo("2026-09-01", summary="Primera llamada, poco interés.", objections=[{"category": "timing", "quote": "Llámame en Q4"}]),
        _memo(
            "2026-09-20",
            summary="Pidió propuesta con precios por usuario.",
            interest="medium",
            objections=[PRICE],
            commitments=[{"text": "Enviar propuesta", "due_at": "2026-09-25T00:00:00Z"}],
            competitors=["Gong"],
        ),
    ])
    lines = text.splitlines()
    assert lines[0] == "Last conversation (2026-09-20): Pidió propuesta con precios por usuario."
    assert "Interest at the end of it: medium" in lines
    assert '- "Es demasiado caro para nosotros ahora mismo" (price, unresolved) — rep answered: "Lo vemos con el ROI del primer trimestre"' in lines
    assert '- "Llámame en Q4" (timing)' in lines
    assert lines.index('- "Es demasiado caro para nosotros ahora mismo" (price, unresolved) — rep answered: "Lo vemos con el ROI del primer trimestre"') < lines.index('- "Llámame en Q4" (timing)')
    assert "- Enviar propuesta (due 2026-09-25)" in lines
    assert "Competitors they mentioned: Gong" in lines


def test_repeated_objection_is_listed_once_and_list_is_capped():
    many = [{"category": "price", "quote": f"objeción {i}"} for i in range(10)]
    text = format_contact_history([_memo("2026-09-02", objections=[PRICE]), _memo("2026-09-03", objections=[PRICE, *many])])
    assert text.count("Es demasiado caro") == 1
    assert text.count('- "') == history_mod.MAX_OBJECTIONS


def test_nothing_stored_means_no_block():
    assert format_contact_history([]) == ""
    assert format_contact_history([{"created_at": "2026-09-01", "extraction": None}]) == ""


class _Query:
    def __init__(self, rows, calls):
        self._rows, self._calls = rows, calls
        self._eq, self._in = {}, {}

    def select(self, cols):
        self._calls.append(("select", cols))
        return self

    def eq(self, col, val):
        self._eq[col] = val
        return self

    def in_(self, col, vals):
        self._in[col] = set(vals)
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, n):
        self._calls.append(("limit", n))
        return self

    def execute(self):
        rows = [r for r in self._rows if all(r.get(k) == v for k, v in self._eq.items())]
        rows = [r for r in rows if all(r.get(k) in v for k, v in self._in.items())]
        return SimpleNamespace(data=sorted(rows, key=lambda r: r["created_at"], reverse=True))


class _Supabase:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def table(self, name):
        assert name == "memos"
        return _Query(self.rows, self.calls)


def _row(day, user="rep-1", **extra):
    return {**_memo(day, summary=f"call {day}"), "company_id": "co-1", "hubspot_contact_id": "901", "user_id": user, **extra}


async def test_loader_skips_internal_memos_and_respects_visibility():
    history_mod._CACHE._values.clear()
    sb = _Supabase([
        _row("2026-09-10", sales_motion_key=INTERNAL_KEY),
        _row("2026-09-05", user="rep-2"),
        _row("2026-09-01"),
    ])
    everyone = await load_contact_history(sb, company_id="co-1", contact_id="901", allowed_user_ids=None)
    assert everyone.startswith("Last conversation (2026-09-05)")

    history_mod._CACHE._values.clear()
    mine = await load_contact_history(sb, company_id="co-1", contact_id="901", allowed_user_ids=["rep-1"])
    assert mine.startswith("Last conversation (2026-09-01)")


async def test_loader_reads_nothing_for_an_empty_author_list_and_never_raises():
    sb = _Supabase([_row("2026-09-01")])
    assert await load_contact_history(sb, company_id="co-1", contact_id="901", allowed_user_ids=[]) == ""
    assert sb.calls == []

    class _Broken:
        def table(self, _):
            raise RuntimeError("db down")

    history_mod._CACHE._values.clear()
    assert await load_contact_history(_Broken(), company_id="co-1", contact_id="777", allowed_user_ids=None) == ""


def _prompt(history=None):
    return build_user_prompt(
        transcript_window="Prospect: es caro",
        latest_turn="es caro",
        product_context="CRM por voz",
        language="es",
        call_mode="softphone",
        contact_history=history,
    )


def test_prompt_carries_the_history_block_only_when_there_is_history():
    assert "THIS CONTACT BEFORE" not in _prompt()
    assert "THIS CONTACT BEFORE" not in _prompt("   ")
    with_history = _prompt("Last conversation (2026-09-20): Pidió propuesta.")
    assert "THIS CONTACT BEFORE" in with_history
    assert with_history.index("THIS CONTACT BEFORE") < with_history.index("ROLLING TRANSCRIPT")


def test_suggest_passes_the_contacts_history_to_the_model(monkeypatch):
    seen = {}

    async def fake_history(_sb, *, company_id, contact_id, allowed_user_ids):
        seen["args"] = (company_id, contact_id, allowed_user_ids)
        return "Last conversation (2026-09-20): Pidió propuesta."

    async def fake_stream(**kwargs):
        seen["contact_history"] = kwargs["contact_history"]
        yield {"type": "result", "suggestion": {}}

    monkeypatch.setattr(copilot_api, "load_contact_history", fake_history)
    monkeypatch.setattr(copilot_api, "stream_objection_suggestion", fake_stream)
    monkeypatch.setattr(copilot_api, "load_company_suggest_grounding", lambda *a, **k: None)
    monkeypatch.setattr(copilot_api, "load_company_knowledge", lambda *a, **k: None)
    monkeypatch.setattr(copilot_api, "_handoff_restricted_user_ids", lambda *a, **k: ["rep-1"])

    app = FastAPI()
    app.include_router(copilot_api.router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id="co-1", user_id="rep-1", role="member", status="active",
    )
    app.dependency_overrides[get_supabase] = lambda: object()
    client = TestClient(app)

    body = {"transcript_window": "x", "latest_turn": "es caro", "call_mode": "softphone"}
    assert client.post("/api/v1/copilot/suggest", json={**body, "contact_id": "901"}).status_code == 200
    assert seen["args"] == ("co-1", "901", ["rep-1"])
    assert seen["contact_history"].startswith("Last conversation")

    seen.clear()
    assert client.post("/api/v1/copilot/suggest", json=body).status_code == 200
    assert "args" not in seen
    assert seen["contact_history"] is None
