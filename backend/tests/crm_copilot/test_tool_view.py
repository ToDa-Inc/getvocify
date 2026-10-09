"""The model reads facts, not bookkeeping."""

import json

from app.services.crm_copilot.tool_view import model_view

PAYLOAD = {
    "coverage": "complete", "observed_at": "2026-09-29T07:59:44.830722+00:00", "n": 2, "n_analysed": 2, "period_days": 30, "period_defaulted": True,
    "connection_rate_pct": None,
    "items": [
        {"memo_id": "m06", "at": "2026-09-27T07:59:44.824045+00:00", "contact_id": "c-hugo", "contact": "Hugo Sanz (Tecno 3)", "interest": None, "objections": [], "obstacles": ["wrong_person"],
         "quotes": [{"quote": "Eso lo lleva mi compañera", "evidence": "ev-69903a8e"}]},
    ],
    "evidence": [{"id": "ev-69903a8e", "memo_id": "m06", "quote": "Eso lo lleva mi compañera"}],
}


def _view(payload):
    return json.loads(model_view(payload))


def test_bookkeeping_and_row_noise_never_reach_the_model():
    body = _view(PAYLOAD)
    assert "observed_at" not in body and "period_defaulted" not in body
    row = body["items"][0]
    assert "memo_id" not in row and "interest" not in row and "objections" not in row
    assert row["at"] == "2026-09-27" and row["contact_id"] == "c-hugo" and row["obstacles"] == ["wrong_person"]


def test_a_top_level_null_stays_because_unknown_is_not_zero():
    assert "connection_rate_pct" in _view(PAYLOAD) and _view(PAYLOAD)["connection_rate_pct"] is None


def test_quotes_are_sent_once_when_the_rows_already_carry_them():
    assert "evidence" not in _view(PAYLOAD)
    only_in_evidence = {**PAYLOAD, "items": [{"contact": "Hugo"}]}
    assert _view(only_in_evidence)["evidence"][0]["id"] == "ev-69903a8e"  # the model needs the id to cite it


def test_the_view_is_compact_and_much_smaller_than_the_payload():
    assert " " not in model_view({"a": 1, "b": [1, 2]}).replace("a", "").replace("b", "")
    assert len(model_view(PAYLOAD)) < len(json.dumps(PAYLOAD, default=str)) * 0.6


def test_a_huge_result_is_cut_rather_than_flooding_the_context():
    assert len(model_view({"rows": ["x" * 100] * 500})) <= 12_000
