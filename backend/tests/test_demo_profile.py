from datetime import datetime, timedelta, timezone

import pytest

from app.services import demo_profile


@pytest.fixture(autouse=True)
def _fresh_cache():
    demo_profile._cache.clear()
    yield
    demo_profile._cache.clear()


OBJECTIONS = [
    {"label": "Precio", "category": "price", "line": "Es caro.", "guidance": "Pregunta por el coste de una parada."},
    {"label": "Otro precio", "category": "price", "line": "Muy caro.", "guidance": "Compara con el coste de un fallo."},
    {"label": "Ya tenemos", "category": "competitor", "line": "Usamos otra.", "guidance": "Pregunta qué le falta."},
    {"label": "Catálogo", "category": "custom", "line": "Mándame el catálogo.", "guidance": "Acepta y propone una llamada."},
    {"label": "Sin guía", "category": "trust", "line": "No me fío.", "guidance": " "},
]


def test_the_first_objection_of_each_fixed_kind_takes_its_own_id_and_the_rest_are_custom():
    entries = demo_profile.entries_from_objections(OBJECTIONS)

    assert [(e["entry_id"], e["category"]) for e in entries] == [
        ("objection:price", "price"),
        ("objection:custom:otro_precio", "custom"),
        ("objection:competitor", "competitor"),
        ("objection:custom:catalogo", "custom"),
    ]
    assert all(e["source_ref"] == "demo" and e["guidance"] for e in entries)


def test_overrides_replace_the_playbook_offer_and_custom_objections():
    profile = demo_profile.profile_from(
        company="Acme Pack", offer="Embotelladoras", knowledge={"value_short": "Menos paradas"}, objections=OBJECTIONS
    )
    over = demo_profile.overrides_for(profile)

    assert over.product_context == "Acme Pack: Embotelladoras"
    assert over.knowledge == {"value_short": "Menos paradas"}
    assert over.snapshot["sales_motion_key"] == "demo" and len(over.snapshot["entries"]) == 4
    assert set(over.custom) == {"objection:custom:otro_precio", "objection:custom:catalogo"}
    assert over.custom["objection:custom:catalogo"]["trigger"] == "Mándame el catálogo."


class _Query:
    def __init__(self, rows):
        self.rows, self.calls = rows, 0

    def select(self, *_):
        return self

    def eq(self, *_):
        return self

    def limit(self, *_):
        return self

    def execute(self):
        self.calls += 1
        return type("R", (), {"data": self.rows})()


class _Supabase:
    def __init__(self, rows):
        self.query = _Query(rows)

    def table(self, _name):
        return self.query


def _row(expires_in_h=1):
    profile = demo_profile.profile_from(company="Acme", offer="Embotelladoras", knowledge={}, objections=OBJECTIONS[:1])
    return {
        "company_id": "c1",
        "profile": profile,
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=expires_in_h)).isoformat(),
    }


def test_active_needs_the_company_flag_and_an_unexpired_row(monkeypatch):
    monkeypatch.setattr(demo_profile, "is_enabled", lambda _sb, cid, flag: (cid, flag) == ("c1", "DEMO_BUYER_ENABLED"))
    assert demo_profile.active(_Supabase([_row()]), "u1").product_context == "Acme: Embotelladoras"

    demo_profile._cache.clear()
    assert demo_profile.active(_Supabase([_row(expires_in_h=-1)]), "u1") is None

    demo_profile._cache.clear()
    monkeypatch.setattr(demo_profile, "is_enabled", lambda *_: False)
    assert demo_profile.active(_Supabase([_row()]), "u1") is None


def test_active_keeps_the_answer_for_a_few_seconds_even_when_there_is_none(monkeypatch):
    monkeypatch.setattr(demo_profile, "is_enabled", lambda *_: True)
    sb = _Supabase([])
    assert demo_profile.active(sb, "u1") is None
    assert demo_profile.active(sb, "u1") is None
    assert sb.query.calls == 1


def test_a_failed_read_is_no_profile_and_is_not_kept(monkeypatch):
    class Broken:
        def table(self, _):
            raise RuntimeError("table missing")

    assert demo_profile.active(Broken(), "u1") is None
    assert "u1" not in demo_profile._cache
