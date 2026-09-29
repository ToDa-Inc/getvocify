"""C04 v7 (PLAYBOOK_QUALIFICATION_ENABLED): one observation per qualification criterion and the
company's own objections matched by id. Flag off, the v5/v6 shapes do not change at all."""

from __future__ import annotations

import asyncio
import json
import os
from types import SimpleNamespace

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-intelligence-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-intelligence-32")

from app.config import settings
from app.services.intelligence import extract
from app.services.intelligence.extract import (
    OBSERVATIONS_PROMPT_VERSION,
    PROMPT_VERSION,
    QUALIFICATION_PROMPT_VERSION,
    _needs_upgrade,
    build_messages,
    extract_intelligence,
    extraction_plan,
    is_current,
    pinned_qualification_inputs,
    playbook_qualification_inputs,
    prompt_path,
    shape_intelligence,
)
from app.services.intelligence.interpret import merge_intelligence

TRANSCRIPT = (
    "You: Hola Daniel, ¿tenéis alguna partida pensada para esto? "
    "Them: Sí, tenemos unos veinte mil euros aprobados para este trimestre. "
    "You: ¿Quién da el visto bueno? Them: Lo firmo yo. "
    "You: Genial, te mando la propuesta. Them: Vale. "
    "Them: Por cierto, mi ERP es propio y no creo que se conecte con vuestra herramienta."
)
MEMO = {"id": "memo-1", "transcript": TRANSCRIPT, "extraction": {"summary": "s"}}
CRITERIA = [
    {"criterion_id": "presupuesto", "label": "Presupuesto"},
    {"criterion_id": "decisor", "label": "Quién decide", "good": "Se sabe quién firma"},
    {"criterion_id": "plazo", "label": "Plazo"},
    {"criterion_id": "necesidad", "label": "Necesidad"},
]
CUSTOM = [{"id": "integracion-erp", "label": "Integración con el ERP", "trigger": "Su ERP no se conecta"}]
ERP_QUOTE = "mi ERP es propio y no creo que se conecte con vuestra herramienta"


def _raw(**extra):
    return {"interest": "medium", "objections": [], "commitments": [], **extra}


def _shape(raw, **kwargs):
    return shape_intelligence(
        MEMO, raw, prompt_version=QUALIFICATION_PROMPT_VERSION,
        playbook_qualification=kwargs.pop("criteria", CRITERIA), playbook_objections=kwargs.pop("custom", CUSTOM),
        **kwargs,
    )


def test_one_observation_per_criterion_in_order_and_only_what_the_transcript_backs():
    shaped = _shape(_raw(qualification_observations=[
        {"criterion_id": "presupuesto", "status": "found", "value": "20.000 € aprobados este trimestre",
         "quote": "tenemos unos veinte mil euros aprobados para este trimestre"},
        {"criterion_id": "decisor", "status": "found", "value": "él mismo", "quote": "Lo firmo yo"},
        {"criterion_id": "plazo", "status": "missing", "quote": "te mando la propuesta"},
        {"criterion_id": "ghost", "status": "found", "quote": "Lo firmo yo"},  # not a playbook criterion
    ]))
    by_id = {obs["criterion_id"]: obs for obs in shaped["qualification_observations"]}
    assert list(by_id) == ["presupuesto", "decisor", "plazo", "necesidad"]
    assert by_id["presupuesto"]["status"] == "found" and by_id["presupuesto"]["value"].startswith("20.000")
    assert by_id["presupuesto"]["evidence_refs"]
    assert by_id["decisor"]["label"] == "Quién decide"
    assert by_id["plazo"]["status"] == "missing" and by_id["plazo"]["value"] is None
    # A criterion the model skipped is unknown, never invented.
    assert by_id["necesidad"]["status"] == "unknown" and by_id["necesidad"]["evidence_refs"] == []
    refs = {e["id"] for e in shaped["evidence"]}
    assert all(ref in refs for obs in by_id.values() for ref in obs["evidence_refs"])


def test_found_needs_the_prospects_own_exact_words_and_missing_needs_an_exact_moment():
    shaped = _shape(_raw(qualification_observations=[
        # invented quote
        {"criterion_id": "presupuesto", "status": "found", "value": "50.000", "quote": "tenemos cincuenta mil"},
        # the REP's words are not the prospect giving the information
        {"criterion_id": "decisor", "status": "found", "value": "no sé", "quote": "¿Quién da el visto bueno?"},
        # missing without an exact moment counts for nothing
        {"criterion_id": "plazo", "status": "missing", "quote": "cuando queráis"},
        # not_applicable never carries a quote or a value
        {"criterion_id": "necesidad", "status": "not_applicable", "value": "x", "quote": "Lo firmo yo"},
    ]))
    by_id = {obs["criterion_id"]: obs for obs in shaped["qualification_observations"]}
    assert by_id["presupuesto"]["status"] == "unknown" and by_id["presupuesto"]["value"] is None
    assert by_id["decisor"]["status"] == "unknown"
    assert by_id["plazo"]["status"] == "unknown"
    assert by_id["necesidad"] == {
        "criterion_id": "necesidad", "label": "Necesidad", "status": "not_applicable",
        "value": None, "quote": None, "evidence_refs": [],
    }


def test_a_bad_status_or_a_long_value_is_cleaned_up():
    long_value = "muy " * 60
    shaped = _shape(_raw(qualification_observations=[
        {"criterion_id": "presupuesto", "status": "maybe", "quote": "Lo firmo yo"},
        {"criterion_id": "decisor", "status": "found", "value": long_value, "quote": "Lo firmo yo"},
    ]))
    by_id = {obs["criterion_id"]: obs for obs in shaped["qualification_observations"]}
    assert by_id["presupuesto"]["status"] == "unknown"
    assert 0 < len(by_id["decisor"]["value"]) <= 80


def test_without_speaker_markers_a_found_quote_counts_on_a_plain_substring():
    memo = {"id": "m", "transcript": "el presupuesto son veinte mil euros y lo decido yo", "extraction": {}}
    shaped = shape_intelligence(
        memo,
        _raw(qualification_observations=[
            {"criterion_id": "presupuesto", "status": "found", "value": "20.000", "quote": "veinte mil euros"},
        ]),
        prompt_version=QUALIFICATION_PROMPT_VERSION,
        playbook_qualification=CRITERIA[:1],
    )
    assert shaped["qualification_observations"][0]["status"] == "found"


def test_a_custom_objection_id_is_kept_only_when_the_playbook_has_it():
    shaped = _shape(_raw(objections=[
        {"kind": "objection", "category": "other", "objection_id": "integracion-erp", "resolution": "open", "quote": ERP_QUOTE},
        {"kind": "objection", "category": "price", "objection_id": "invented-one", "resolution": "open",
         "quote": "veinte mil euros aprobados"},
        {"kind": "obstacle", "category": "bad_moment", "objection_id": "integracion-erp", "resolution": "open",
         "quote": "Lo firmo yo"},
        {"kind": "objection", "category": "trust", "resolution": "open", "quote": "Vale"},
    ]))
    by_quote = {o["quote"]: o for o in shaped["objections"]}
    assert by_quote[ERP_QUOTE]["objection_id"] == "integracion-erp"
    assert by_quote[ERP_QUOTE]["category"] == "other"  # the category stays one of the fixed ones
    assert by_quote["veinte mil euros aprobados"]["objection_id"] is None
    assert by_quote["Lo firmo yo"]["objection_id"] is None  # an obstacle is never a custom objection
    assert by_quote["Vale"]["objection_id"] is None


def test_without_custom_objections_no_id_is_ever_kept():
    shaped = shape_intelligence(
        MEMO,
        _raw(objections=[{"kind": "objection", "category": "other", "objection_id": "x", "resolution": "open", "quote": ERP_QUOTE}]),
        prompt_version=QUALIFICATION_PROMPT_VERSION,
    )
    assert shaped["objections"][0]["objection_id"] is None
    assert shaped["qualification_observations"] == []


def test_v7_keeps_everything_v6_reads():
    shaped = _shape(_raw(
        competitor_mentions=[{"name": "Ringover", "quote": "Lo firmo yo"}],
        playbook_observations=[{"step_id": "s1", "status": "met", "quote": "te mando la propuesta"}],
    ), playbook_steps=[{"step_id": "s1", "label": "Cierre", "criterion": "Propone el siguiente paso"}])
    assert shaped["prompt_version"] == QUALIFICATION_PROMPT_VERSION
    assert [c["name"] for c in shaped["competitor_mentions"]] == ["Ringover"]
    assert shaped["playbook_observations"][0]["status"] == "met"


def test_flag_off_versions_keep_their_exact_shape():
    raw = _raw(
        objections=[{"kind": "objection", "category": "price", "objection_id": "integracion-erp", "resolution": "open", "quote": ERP_QUOTE}],
        qualification_observations=[{"criterion_id": "presupuesto", "status": "found", "quote": "Lo firmo yo"}],
    )
    for version in (PROMPT_VERSION, OBSERVATIONS_PROMPT_VERSION):
        shaped = shape_intelligence(
            MEMO, raw, prompt_version=version, playbook_qualification=CRITERIA, playbook_objections=CUSTOM,
        )
        assert "qualification_observations" not in shaped
        assert all("objection_id" not in obj for obj in shaped["objections"])
        assert shaped["prompt_version"] == version


def test_v7_sends_qualification_and_custom_objections_and_older_versions_do_not():
    payload = json.loads(build_messages(
        MEMO, prompt_version=QUALIFICATION_PROMPT_VERSION,
        playbook_steps=[{"step_id": "s1", "label": "Cierre", "criterion": "c"}],
        playbook_qualification=CRITERIA, playbook_objections=CUSTOM,
    )[1]["content"])
    assert payload["playbook_qualification"][0] == {"criterion_id": "presupuesto", "label": "Presupuesto"}
    assert payload["playbook_qualification"][1]["good"] == "Se sabe quién firma"
    assert payload["playbook_objections"] == [
        {"id": "integracion-erp", "label": "Integración con el ERP", "trigger": "Su ERP no se conecta"},
    ]
    assert payload["playbook_steps"][0]["step_id"] == "s1"
    for version in (PROMPT_VERSION, OBSERVATIONS_PROMPT_VERSION):
        old = json.loads(build_messages(
            MEMO, prompt_version=version, playbook_qualification=CRITERIA, playbook_objections=CUSTOM,
        )[1]["content"])
        assert "playbook_qualification" not in old and "playbook_objections" not in old
    empty = json.loads(build_messages(MEMO, prompt_version=QUALIFICATION_PROMPT_VERSION)[1]["content"])
    assert "playbook_qualification" not in empty and "playbook_objections" not in empty


def test_the_v7_prompt_is_v6_plus_the_new_sections():
    v6 = prompt_path(OBSERVATIONS_PROMPT_VERSION).read_text(encoding="utf-8")
    v7 = prompt_path(QUALIFICATION_PROMPT_VERSION).read_text(encoding="utf-8")
    for needle in ("qualification_observations", "objection_id", "playbook_qualification", "playbook_objections",
                   "found", "missing", "not_applicable"):
        assert needle in v7
    assert 'kind "obstacle"' in v7 and "never price or timing objections" in v7
    # every line of v6 is still there (the two edits are the input list and the JSON template)
    v6_body = [line for line in v6.splitlines() if line.strip() and "playbook_steps" not in line and "competitor_mentions\": []" not in line]
    v7_lines = set(v7.splitlines())
    assert all(line in v7_lines for line in v6_body if "Lines start" not in line)
    assert v6 != v7


def test_v7_counts_as_current_and_upgrades_older_blocks_only():
    assert QUALIFICATION_PROMPT_VERSION in extract.CURRENT_PROMPT_VERSIONS
    for stored in (PROMPT_VERSION, OBSERVATIONS_PROMPT_VERSION):
        old = {"extraction": {"intelligence": {"prompt_version": stored}}}
        assert _needs_upgrade(old, QUALIFICATION_PROMPT_VERSION) is True
    v7 = {"extraction": {"intelligence": {"prompt_version": QUALIFICATION_PROMPT_VERSION}}}
    assert _needs_upgrade(v7, QUALIFICATION_PROMPT_VERSION) is False
    assert _needs_upgrade(v7, OBSERVATIONS_PROMPT_VERSION) is False  # never downgraded when the flag goes off
    assert _needs_upgrade(v7, PROMPT_VERSION) is False


def test_the_pinned_version_still_keys_the_input_revision():
    """Versions are immutable: a new criterion or custom objection is a new version id, which is
    already in the C04 revision, so a memo pinned to it is read again."""
    from app.services.intelligence.worker import revision_for_memo

    a = revision_for_memo({**MEMO, "playbook_version_id": "pv-1"})
    b = revision_for_memo({**MEMO, "playbook_version_id": "pv-2"})
    assert a != b
    memo = {**MEMO, "playbook_version_id": "pv-1", "extraction": {"summary": "s", "intelligence": {
        "prompt_version": QUALIFICATION_PROMPT_VERSION, "input_revision": a}}}
    assert is_current(memo)
    assert not is_current({**memo, "playbook_version_id": "pv-2"})


def test_criteria_and_custom_objections_come_from_the_pinned_version():
    rows = [{
        "qualification": [
            {"criterion_id": "presupuesto", "label": "Presupuesto", "why": "w", "good": "Sabe la partida", "bad": "b"},
            {"criterion_id": "presupuesto", "label": "Duplicado"},
            {"criterion_id": "", "label": "Sin id"},
            {"criterion_id": "sin-label", "label": ""},
            "junk",
        ],
        "entries": [
            {"entry_id": "objection:price", "category": "price", "guidance": "g"},
            {"entry_id": "objection:custom:integracion-erp", "category": "custom", "label": "Integración con el ERP",
             "trigger": "Su ERP no se conecta", "guidance": "g"},
            {"entry_id": "objection:custom:sin-label", "category": "custom"},
            {"entry_id": "objection:custom:", "category": "custom", "label": "x"},
        ],
    }]
    criteria, custom = playbook_qualification_inputs(rows)
    assert criteria == [{"criterion_id": "presupuesto", "label": "Presupuesto", "good": "Sabe la partida"}]
    assert custom == [{"id": "integracion-erp", "label": "Integración con el ERP", "trigger": "Su ERP no se conecta"}]


def test_the_lists_are_capped_at_the_playbook_limits():
    rows = [{
        "qualification": [{"criterion_id": f"c{i}", "label": f"C{i}"} for i in range(12)],
        "entries": [
            {"entry_id": f"objection:custom:o{i}", "category": "custom", "label": f"O{i}", "trigger": "t"} for i in range(20)
        ],
    }]
    criteria, custom = playbook_qualification_inputs(rows)
    assert len(criteria) == 8 and len(custom) == 12


def test_a_missing_or_empty_qualification_is_tolerated():
    assert playbook_qualification_inputs([]) == ([], [])
    assert playbook_qualification_inputs([{"entries": None, "qualification": None}]) == ([], [])
    assert playbook_qualification_inputs([{"entries": [{"entry_id": "objection:price", "category": "price"}]}]) == ([], [])


class _Table:
    def __init__(self, rows, fail_on=()):
        self.rows, self.fail_on, self.selected = rows, fail_on, []

    def select(self, columns):
        self.selected.append(columns)
        self._columns = columns
        return self

    def eq(self, *_args):
        return self

    def limit(self, *_args):
        return self

    def execute(self):
        if self._columns in self.fail_on:
            raise RuntimeError('column "qualification" does not exist')
        return SimpleNamespace(data=self.rows)


class _Supabase:
    def __init__(self, table):
        self._table = table

    def table(self, name):
        assert name == "playbook_versions"
        return self._table


def test_a_database_without_the_qualification_column_still_gives_the_custom_objections():
    table = _Table(
        [{"entries": [{"entry_id": "objection:custom:erp", "category": "custom", "label": "ERP", "trigger": "t"}]}],
        fail_on=("qualification,entries",),
    )
    criteria, custom = pinned_qualification_inputs(_Supabase(table), {"playbook_version_id": "pv-1"})
    assert criteria == [] and custom[0]["id"] == "erp"
    assert table.selected == ["qualification,entries", "entries"]


def test_nothing_pinned_or_an_unreadable_version_gives_nothing():
    assert pinned_qualification_inputs(_Supabase(_Table([])), {}) == ([], [])
    table = _Table([], fail_on=("qualification,entries", "entries"))
    assert pinned_qualification_inputs(_Supabase(table), {"playbook_version_id": "pv-1"}) == ([], [])


def test_the_flag_picks_the_prompt_version(monkeypatch):
    memo = {"company_id": "co-1", "playbook_version_id": "pv-1"}
    monkeypatch.setattr(extract, "pinned_playbook_steps", lambda _s, _m: [{"step_id": "s1"}])

    def plan(flags):
        monkeypatch.setattr(
            "app.services.feature_flags.is_enabled", lambda _s, _c, flag: flag in flags,
        )
        return extraction_plan(object(), memo)

    assert plan(set()) == (PROMPT_VERSION, [])
    assert plan({"PLAYBOOK_OBSERVATIONS_ENABLED"}) == (OBSERVATIONS_PROMPT_VERSION, [{"step_id": "s1"}])
    assert plan({"PLAYBOOK_QUALIFICATION_ENABLED"}) == (QUALIFICATION_PROMPT_VERSION, [{"step_id": "s1"}])
    assert plan({"PLAYBOOK_QUALIFICATION_ENABLED", "PLAYBOOK_OBSERVATIONS_ENABLED"})[0] == QUALIFICATION_PROMPT_VERSION


def test_the_flag_exists_and_is_off_by_default():
    assert settings.PLAYBOOK_QUALIFICATION_ENABLED is False


def test_extract_intelligence_passes_the_inputs_to_the_model_and_shapes_v7():
    seen = {}

    class LLM:
        last_call_meta = {}

        async def chat_json(self, messages, **_kwargs):
            seen["payload"] = json.loads(messages[1]["content"])
            return _raw(
                objections=[{"kind": "objection", "category": "other", "objection_id": "integracion-erp",
                             "resolution": "open", "quote": ERP_QUOTE}],
                qualification_observations=[
                    {"criterion_id": "decisor", "status": "found", "value": "él mismo", "quote": "Lo firmo yo"},
                ],
            )

    shaped, _meta = asyncio.run(extract_intelligence(
        MEMO, LLM(), prompt_version=QUALIFICATION_PROMPT_VERSION,
        playbook_qualification=CRITERIA[1:2], playbook_objections=CUSTOM,
    ))
    assert seen["payload"]["playbook_qualification"][0]["criterion_id"] == "decisor"
    assert seen["payload"]["playbook_objections"][0]["id"] == "integracion-erp"
    assert shaped["objections"][0]["objection_id"] == "integracion-erp"
    assert shaped["qualification_observations"][0]["status"] == "found"


def test_a_v7_block_keeps_its_qualification_when_the_classifier_merges_in():
    existing = {
        "input_revision": "r", "prompt_version": QUALIFICATION_PROMPT_VERSION, "status": "ready",
        "meeting": {}, "evidence": [], "objections": [],
        "qualification_observations": [{"criterion_id": "presupuesto", "status": "found"}],
    }
    incoming = {"input_revision": "r", "status": "partial", "pain_confirmed": True, "meeting": {"agreed": None}, "evidence": []}
    merged = merge_intelligence(existing, incoming)
    assert merged["qualification_observations"][0]["criterion_id"] == "presupuesto"
    assert merged["pain_confirmed"] is True
