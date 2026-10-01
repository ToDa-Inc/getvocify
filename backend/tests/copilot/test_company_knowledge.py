"""The live copilot gets the company's own knowledge as the only proof it may cite, bounded in size."""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-copilot-32-chars")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-copilot-32-chars")

from app.services.copilot.load_grounding import load_company_knowledge
from app.services.copilot.prompts import (
    COMPANY_KNOWLEDGE_MAX_CHARS,
    SYSTEM_PROMPT,
    build_user_prompt,
    format_company_knowledge,
)

KNOWLEDGE = {
    "value_short": "Vocify prepara cada llamada y dice qué falta en ella.",
    "value_long": "TEXTO LARGO QUE NO VA AL PROMPT",
    "pricing": "PRECIOS QUE NO VAN AL PROMPT",
    "differentiators": ["Lee la llamada y no solo la transcribe", "Se conecta a HubSpot en un día"],
    "proofs": [
        {"customer": "Logística Norte", "change": "Subió la conversión"},
        {"customer": "Clínica Sur", "change": "Citas +30 %"},
        {"customer": "Talleres Vega", "change": "c"},
        {"customer": "CUARTO CASO", "change": "c"},
    ],
    "competitors": [
        {"name": "Ringover", "how_to_talk": "Reconoce que es buena telefonía; nosotros leemos la llamada."},
        {"name": "Gong", "how_to_talk": "GONG HOW"},
    ],
}


def _prompt(knowledge, *, latest="Them: ya usamos Ringover", window="You: hola. Them: ya usamos Ringover"):
    return build_user_prompt(
        transcript_window=window, latest_turn=latest, product_context=None, language="es",
        call_mode="softphone", company_knowledge=knowledge,
    )


def test_the_block_is_marked_as_the_only_allowed_proof():
    text = format_company_knowledge(KNOWLEDGE)
    assert text.startswith("COMPANY KNOWLEDGE")
    assert "ONLY proof" in text
    assert "Value in one line: Vocify prepara cada llamada" in text
    assert "- Lee la llamada y no solo la transcribe" in text
    assert "Logística Norte" in text and "Subió la conversión" in text
    assert "COMPANY KNOWLEDGE block" in SYSTEM_PROMPT  # the rule against inventing proof points at it


def test_only_three_proofs_and_no_unrelated_fields():
    text = format_company_knowledge(KNOWLEDGE)
    assert "Talleres Vega" in text and "CUARTO CASO" not in text
    for leaked in ("TEXTO LARGO", "PRECIOS", "NO VA"):
        assert leaked not in text


def test_a_competitor_is_included_only_when_named_in_the_call():
    text = format_company_knowledge(KNOWLEDGE, call_text="Them: ya usamos ringover para llamar")
    assert "Competitor named in the call: Ringover" in text
    assert "How to win against it: Reconoce que es buena telefonía" in text
    assert "Gong" not in text and "GONG" not in text
    assert "Competitor named" not in format_company_knowledge(KNOWLEDGE, call_text="Them: es caro")


def test_the_block_is_bounded_whatever_the_company_wrote():
    huge = {
        "value_short": "v" * 5000,
        "differentiators": ["d" * 800] * 12,
        "proofs": [{"customer": "c" * 500, "situation": "s" * 900, "change": "x" * 900, "number": "n" * 500}] * 12,
        "competitors": [{"name": "Ringover", "how_to_talk": "h" * 3000, "landmines": "l" * 3000}],
    }
    text = format_company_knowledge(huge, call_text="ringover")
    assert 0 < len(text) <= COMPANY_KNOWLEDGE_MAX_CHARS
    assert len(format_company_knowledge(huge, call_text="ringover", max_chars=500)) <= 500
    assert len(_prompt(huge)) < 8000 + COMPANY_KNOWLEDGE_MAX_CHARS


def test_each_field_is_truncated_on_its_own():
    text = format_company_knowledge({"value_short": "v" * 1000, "differentiators": ["d" * 500]})
    value_line = next(line for line in text.splitlines() if line.startswith("Value in one line"))
    assert len(value_line) <= len("Value in one line: ") + 300
    assert value_line.endswith("…")


def test_nothing_to_say_gives_nothing():
    for empty in (None, {}, {"notes": "solo notas"}, {"differentiators": [], "proofs": [{}], "competitors": []}, "no es dict"):
        assert format_company_knowledge(empty) == ""


def test_the_prompt_carries_the_block_after_the_product_context_and_is_unchanged_without_it():
    with_block = _prompt(KNOWLEDGE)
    assert with_block.index("PRODUCT / OFFER CONTEXT") < with_block.index("COMPANY KNOWLEDGE") < with_block.index("ROLLING TRANSCRIPT")
    assert "Ringover" in with_block and "GONG" not in with_block
    without = _prompt(None)
    assert "COMPANY KNOWLEDGE" not in without
    assert _prompt({}) == without
    assert without == build_user_prompt(
        transcript_window="You: hola. Them: ya usamos Ringover", latest_turn="Them: ya usamos Ringover",
        product_context=None, language="es", call_mode="softphone",
    )


def test_a_competitor_named_only_earlier_in_the_window_still_counts():
    prompt = _prompt(KNOWLEDGE, latest="Them: es que no me convence", window="Them: usamos Gong. You: ok. Them: no me convence")
    assert "GONG HOW" in prompt and "Ringover" not in prompt.split("ROLLING TRANSCRIPT")[0]


class _Chain:
    def __init__(self, rows=None, error=None):
        self.rows, self.error, self.called = rows or [], error, []

    def table(self, name):
        self.called.append(name)
        return self

    def select(self, *_a):
        return self

    def eq(self, *_a):
        return self

    def limit(self, *_a):
        return self

    def execute(self):
        if self.error:
            raise self.error
        return SimpleNamespace(data=self.rows)


def test_the_loader_reads_the_company_row():
    client = _Chain([{"data": {"value_short": "x"}}])
    assert load_company_knowledge(client, company_id="co-1") == {"value_short": "x"}
    assert client.called == ["company_sales_knowledge"]


def _suggest(monkeypatch, supabase):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import copilot as copilot_api
    from app.deps import get_membership, get_supabase
    from app.services.company import Membership

    seen = {}

    async def fake_stream(**kwargs):
        seen.update(kwargs)
        yield {"type": "result", "suggestion": {}}

    monkeypatch.setattr(copilot_api, "stream_objection_suggestion", fake_stream)
    monkeypatch.setattr(copilot_api, "load_company_suggest_grounding", lambda *_a, **_k: None)
    app = FastAPI()
    app.include_router(copilot_api.router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id="co-1", user_id="u-1", role="member", status="active",
    )
    app.dependency_overrides[get_supabase] = lambda: supabase
    response = TestClient(app).post(
        "/api/v1/copilot/suggest", json={"transcript_window": "Them: caro", "latest_turn": "Them: caro"},
    )
    assert response.status_code == 200
    return seen


def test_the_suggest_route_hands_the_company_knowledge_to_the_prompt(monkeypatch):
    seen = _suggest(monkeypatch, _Chain([{"data": {"value_short": "x"}}]))
    assert seen["company_knowledge"] == {"value_short": "x"}


def test_the_suggest_route_works_when_the_table_is_missing(monkeypatch):
    seen = _suggest(monkeypatch, _Chain(error=RuntimeError("relation does not exist")))
    assert seen["company_knowledge"] is None


def test_a_missing_table_no_row_or_a_bad_row_gives_none():
    assert load_company_knowledge(_Chain(error=RuntimeError('relation "company_sales_knowledge" does not exist')), company_id="c") is None
    assert load_company_knowledge(_Chain([]), company_id="c") is None
    assert load_company_knowledge(_Chain([{"data": {}}]), company_id="c") is None
    assert load_company_knowledge(_Chain([{"data": "texto"}]), company_id="c") is None
    assert load_company_knowledge(_Chain([{"data": None}]), company_id="c") is None
