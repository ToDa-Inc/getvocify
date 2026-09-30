"""PLAYBOOK_QUALIFICATION_ENABLED: the score is three blocks (steps, qualification, objections)
and «No salió: …» coaching for a criterion that never came out. Flag off, nothing changes."""

from __future__ import annotations

import copy
import json
import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-coaching-32-chars")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-coaching-32-chars")

import pytest

from app.services.coaching.score_assembly import (
    attach_score_to_job_payload,
    blocks_value,
    build_score_from_extraction,
    coaching_lines,
    qualification_improvements,
    score_blocks,
)
from app.services.coaching.briefs import label_missed_items

MEMO = {"id": "memo-1", "playbook_version_id": "pv-1", "screening_outcome": None,
        "transcript": "You: Hola. Them: Hola, dime."}


def _ev(ref):
    return {"id": ref, "source_type": "transcript", "source_id": "memo-1", "quote": f"cita {ref}"}


def _step(step_id, status, ref=None):
    return {"step_id": step_id, "label": step_id.title(), "criterion": f"criterio de {step_id}", "status": status,
            "quote": None, "evidence_refs": [ref] if ref else []}


def _qual(criterion_id, status, ref=None, label=None):
    return {"criterion_id": criterion_id, "label": criterion_id.title() if label is None else label, "status": status,
            "value": None, "quote": None, "evidence_refs": [ref] if ref else []}


def _objection(ref, *, resolved, category="price", objection_id=None, replied=True):
    item = {
        "id": f"obj-{ref}", "kind": "objection", "category": category,
        "resolution": "resolved" if resolved else "open", "evidence_refs": [ref],
        "response_evidence_refs": [f"{ref}-r"] if resolved else [], "rep_replied_after": replied,
    }
    if objection_id:
        item["objection_id"] = objection_id
    return item


def _extraction(*, steps=(), qualification=(), objections=(), refs=(), version=1):
    return {
        "summary": "Llamada",
        "intelligence": {
            "version": version, "input_revision": "rev-1",
            "playbook_observations": list(steps),
            "qualification_observations": list(qualification),
            "objections": list(objections),
            "evidence": [_ev(ref) for ref in refs],
        },
    }


def _score(extraction, **flags):
    return build_score_from_extraction(extraction=extraction, memo=MEMO, input_revision="rev-1", **flags)


# ---------------------------------------------------------------- flag off

def test_flag_off_ignores_qualification_and_adds_no_blocks():
    extraction = _extraction(
        steps=[_step("apertura", "met", "e1"), _step("cierre", "missed", "e2")],
        qualification=[_qual("presupuesto", "missing", "e3"), _qual("decisor", "found", "e4")],
        refs=["e1", "e2", "e3", "e4"],
    )
    base = copy.deepcopy(extraction)
    for block in (base["intelligence"],):
        block.pop("qualification_observations")
    off = _score(extraction)
    assert off == _score(base)
    assert "blocks" not in off and "missed_items" not in off
    assert off["met_steps"] == 1 and off["missed_steps"] == 1 and off["value"] == 5
    assert all("No salió" not in line for line in off["improvements"])


def test_flag_off_is_byte_identical_to_the_pre_flag_output():
    extraction = _extraction(steps=[_step("apertura", "met", "e1"), _step("cierre", "missed", "e2")], refs=["e1", "e2"])
    explicit = _score(extraction, qualification_enabled=False)
    default = _score(extraction)
    assert json.dumps(explicit, sort_keys=True) == json.dumps(default, sort_keys=True)
    assert set(default) == {
        "status", "value", "reason", "crm_outcome", "playbook_version_id", "input_revision", "prompt_version",
        "met_steps", "missed_steps", "applicable_steps", "unknown_steps", "not_applicable_steps",
        "adherence", "coverage", "strengths", "improvements",
        # Not a qualification key: a missed step's line is cited, so the brief may show it.
        "improvements_cited",
    }


def test_flag_off_with_objection_credit_keeps_todays_missed_items():
    extraction = _extraction(objections=[_objection("e1", resolved=False, objection_id="erp")], refs=["e1"])
    score = _score(extraction, objection_credit_enabled=True)
    assert score["missed_items"] == [{"kind": "objection", "id": "obj-e1", "category": "price"}]  # no objection_id


def test_flag_off_does_not_score_a_v7_block_that_only_has_qualification():
    extraction = {"summary": "", "intelligence": {
        "version": 1, "input_revision": "rev-1", "objections": [], "playbook_observations": [],
        "qualification_observations": [_qual("presupuesto", "found", "e1")], "evidence": [_ev("e1")]}}
    assert _score(extraction) is None
    assert _score(extraction, qualification_enabled=True) is not None


# ---------------------------------------------------------------- flag on

def test_qualification_observations_become_criteria():
    extraction = _extraction(
        steps=[_step("apertura", "met", "e1")],
        qualification=[
            _qual("presupuesto", "found", "e2"), _qual("decisor", "missing", "e3"),
            _qual("plazo", "not_applicable"), _qual("necesidad", "unknown"),
        ],
        refs=["e1", "e2", "e3"],
    )
    score = _score(extraction, qualification_enabled=True)
    # 1 step met + found(met) + missing(missed); not_applicable / unknown as today
    assert (score["met_steps"], score["missed_steps"], score["applicable_steps"]) == (2, 1, 3)
    assert score["unknown_steps"] == 1 and score["not_applicable_steps"] == 1
    assert score["blocks"] == {
        "steps": {"met": 1, "applicable": 1},
        "qualification": {"met": 1, "applicable": 2},
        "objections": {"met": 0, "applicable": 0},
    }
    assert score["value"] == 8  # mean(1.0, 0.5) = 0.75 -> 7.5 -> 8
    assert score["status"] == "ready"


def test_a_found_or_missing_without_backed_evidence_is_unknown_not_a_miss():
    extraction = _extraction(
        qualification=[_qual("presupuesto", "found"), _qual("decisor", "missing"), _qual("plazo", "found", "e1")],
        refs=["e1"],
    )
    score = _score(extraction, qualification_enabled=True)
    assert score["blocks"]["qualification"] == {"met": 1, "applicable": 1}
    assert score["unknown_steps"] == 2
    assert score["improvements"] == []


def test_missing_criteria_add_a_deterministic_not_found_line_in_spanish_by_default():
    extraction = _extraction(
        steps=[_step("cierre", "missed", "e1")],
        qualification=[_qual("presupuesto", "missing", "e2", label="Presupuesto"), _qual("decisor", "missing", "e3", label="Quién decide")],
        refs=["e1", "e2", "e3"],
    )
    score = _score(extraction, qualification_enabled=True)
    assert score["improvements"] == [
        "Cierre: criterio de cierre", "No salió: Presupuesto", "No salió: Quién decide",
    ]
    assert _score(extraction, qualification_enabled=True) == score  # deterministic


def test_the_not_found_line_follows_the_language_of_the_conversation():
    extraction = _extraction(qualification=[_qual("budget", "missing", "e1", label="Budget")], refs=["e1"])
    english = {**MEMO, "transcript": "You: What is your budget for this? Them: We have not thought about the budget yet, "
                                     "and the team is the one that has to decide what they need for the year."}
    score = build_score_from_extraction(
        extraction=extraction, memo=english, input_revision="rev-1", qualification_enabled=True,
    )
    assert score["improvements"] == ["Not found out: Budget"]


def test_qualification_improvements_helper_skips_unbacked_and_unlabeled():
    intelligence = {"evidence": [_ev("e1")], "qualification_observations": [
        _qual("a", "missing", "e1", label="A"), _qual("b", "missing", "ghost", label="B"),
        _qual("c", "missing", "e1", label=" "), _qual("d", "found", "e1", label="D"),
    ]}
    assert qualification_improvements(intelligence, evidence_ids=["e1"]) == ["No salió: A"]
    assert qualification_improvements(intelligence, evidence_ids=["e1"], language="en") == ["Not found out: A"]


def test_missed_items_carry_the_criterion_and_the_custom_objection_id():
    extraction = _extraction(
        qualification=[_qual("presupuesto", "missing", "e1", label="Presupuesto")],
        objections=[_objection("e2", resolved=False, objection_id="integracion-erp")],
        refs=["e1", "e2"],
    )
    score = _score(extraction, qualification_enabled=True)
    assert score["missed_items"] == [
        {"kind": "qualification", "id": "presupuesto", "label": "Presupuesto"},
        {"kind": "objection", "id": "obj-e2", "category": "price", "objection_id": "integracion-erp"},
    ]


def test_the_objections_block_counts_the_objections_the_rep_faced():
    extraction = _extraction(
        objections=[_objection("e1", resolved=True), _objection("e2", resolved=False), _objection("e3", resolved=False, replied=None)],
        refs=["e1", "e1-r", "e2", "e3"],
    )
    score = _score(extraction, qualification_enabled=True)
    assert score["blocks"]["objections"] == {"met": 1, "applicable": 2}
    assert score["value"] == 5  # only one block has something to judge
    assert score["status"] == "ready"


def test_blocks_math():
    blocks = score_blocks(["met", "missed", "unknown", "not_applicable"], ["met", "met", "missed", "missed"], [])
    assert blocks == {
        "steps": {"met": 1, "applicable": 2},
        "qualification": {"met": 2, "applicable": 4},
        "objections": {"met": 0, "applicable": 0},
    }
    assert blocks_value(blocks) == 5  # mean(0.5, 0.5)
    everything = {"steps": {"met": 3, "applicable": 4}, "qualification": {"met": 1, "applicable": 2},
                  "objections": {"met": 1, "applicable": 1}}
    assert blocks_value(everything) == 8  # mean(.75, .5, 1) = .75 -> 7.5 -> 8 (round half to even)
    # a block with nothing applicable is left out of the mean, not counted as zero
    assert blocks_value({"steps": {"met": 0, "applicable": 0}, "qualification": {"met": 2, "applicable": 2},
                         "objections": {"met": 0, "applicable": 0}}) == 10
    assert blocks_value({"steps": {"met": 0, "applicable": 3}, "qualification": {"met": 0, "applicable": 0},
                         "objections": {"met": 0, "applicable": 0}}) == 0


def test_no_block_with_anything_applicable_means_no_mark():
    zero = {name: {"met": 0, "applicable": 0} for name in ("steps", "qualification", "objections")}
    assert blocks_value(zero) is None
    extraction = _extraction(
        steps=[_step("apertura", "unknown")], qualification=[_qual("presupuesto", "unknown"), _qual("plazo", "not_applicable")],
    )
    score = _score(extraction, qualification_enabled=True)
    assert score["value"] is None and score["status"] == "partial" and score["reason"] == "insufficient_evidence"
    assert score["blocks"] == zero


def test_a_voicemail_gets_no_mark_even_with_blocks():
    extraction = _extraction(qualification=[_qual("presupuesto", "found", "e1")], refs=["e1"])
    score = build_score_from_extraction(
        extraction=extraction, memo={**MEMO, "screening_outcome": "voicemail"}, input_revision="rev-1",
        qualification_enabled=True,
    )
    assert score["value"] is None
    assert score["blocks"]["qualification"] == {"met": 1, "applicable": 1}


def test_a_crm_outcome_still_does_not_move_the_mark():
    extraction = _extraction(qualification=[_qual("presupuesto", "found", "e1")], refs=["e1"])
    won = _score(extraction, qualification_enabled=True, crm_outcome="closed_won")
    lost = _score(extraction, qualification_enabled=True, crm_outcome="closed_lost")
    assert won["value"] == lost["value"] == 10


def test_attach_score_to_job_payload_passes_the_flag_through():
    extraction = _extraction(qualification=[_qual("presupuesto", "missing", "e1", label="Presupuesto")], refs=["e1"])
    payload = {"version": 1, "input_revision": "rev-1", **extraction["intelligence"]}
    on = attach_score_to_job_payload(MEMO, payload, extraction=extraction, qualification_enabled=True)
    off = attach_score_to_job_payload(MEMO, payload, extraction=extraction)
    assert on["score"]["blocks"]["qualification"] == {"met": 0, "applicable": 1}
    assert "blocks" not in off.get("score", {})


def test_coaching_lines_for_steps_are_untouched_by_qualification():
    intelligence = _extraction(steps=[_step("cierre", "missed", "e1")], qualification=[_qual("p", "missing", "e2")],
                               refs=["e1", "e2"])["intelligence"]
    assert coaching_lines(intelligence, evidence_ids=["e1", "e2"]) == ([], ["Cierre: criterio de cierre"])


@pytest.mark.parametrize("step_statuses,expected", [
    ([], None),
    (["met"], 10),
    (["missed"], 0),
])
def test_steps_alone_under_the_flag_keep_the_old_scale(step_statuses, expected):
    steps = [_step(f"s{i}", status, "e1" if status in {"met", "missed"} else None) for i, status in enumerate(step_statuses)]
    extraction = _extraction(steps=steps, refs=["e1"]) if steps else {"summary": "x", "intelligence": {"evidence": []}}
    score = _score(extraction, qualification_enabled=True)
    assert score["value"] == expected


# ---------------------------------------------------------------- missed labels and API

def test_missed_labels_for_qualification_and_custom_objections():
    # What to say is the step's example phrase; the criterion is only how the step is judged.
    steps = [{"step_id": "cierre", "label": "Cierre", "criterion": "Propone el paso siguiente",
              "example": "¿Lo vemos el jueves a las 10?"}]
    entries = [
        {"entry_id": "objection:price", "category": "price", "guidance": "Habla de valor"},
        {"entry_id": "objection:custom:integracion-erp", "category": "custom", "label": "Integración con el ERP",
         "guidance": "Tenemos API abierta"},
    ]
    labeled = label_missed_items(
        [
            {"kind": "step", "id": "cierre"},
            {"kind": "qualification", "id": "presupuesto", "label": "Presupuesto"},
            {"kind": "objection", "id": "obj-1", "category": "other", "objection_id": "integracion-erp"},
            {"kind": "objection", "id": "obj-2", "category": "price"},
            {"kind": "objection", "id": "obj-3", "category": "other", "objection_id": "borrada"},
        ],
        steps=steps, entries=entries,
    )
    assert labeled == [
        {"id": "cierre", "kind": "step", "label": "Cierre", "guidance": "¿Lo vemos el jueves a las 10?"},
        {"id": "presupuesto", "kind": "qualification", "label": "Presupuesto"},
        {"id": "obj-1", "kind": "objection", "label": "Integración con el ERP", "guidance": "Tenemos API abierta"},
        {"id": "obj-2", "kind": "objection", "label": "price", "guidance": "Habla de valor"},
    ]


def _client(score_row):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import coaching as coaching_api
    from app.deps import get_membership, get_supabase
    from app.services.company import Membership

    class Result:
        def __init__(self, data):
            self.data = data

    class Query:
        def __init__(self, rows):
            self.rows, self.filters = rows, []

        def select(self, *_a, **_k):
            return self

        def eq(self, column, value):
            self.filters.append((column, value))
            return self

        def execute(self):
            rows = self.rows
            for column, value in self.filters:
                rows = [row for row in rows if row.get(column) == value]
            return Result(rows)

    class Store:
        def table(self, name):
            if name == "memos":
                return Query([{"id": "memo-1", "company_id": "co-1", "user_id": "user-a"}])
            return Query(score_row)

    app = FastAPI()
    app.include_router(coaching_api.router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id="co-1", user_id="user-a", role="member", status="active",
    )
    app.dependency_overrides[get_supabase] = lambda: Store()
    return TestClient(app)


def test_the_memo_score_endpoint_passes_blocks_through():
    blocks = {"steps": {"met": 1, "applicable": 2}, "qualification": {"met": 1, "applicable": 1},
              "objections": {"met": 0, "applicable": 0}}
    body = _client([{
        "memo_id": "memo-1", "revision_seq": 1, "playbook_version_id": "pv-1",
        "score": {"status": "ready", "value": 8, "blocks": blocks, "improvements": ["No salió: Presupuesto"]},
    }]).get("/api/v1/memos/memo-1/score").json()
    assert body["blocks"] == blocks
    assert body["improvements"] == ["No salió: Presupuesto"]


def test_a_rescored_memo_with_the_same_seq_shows_the_latest_write():
    rows = [
        {"memo_id": "memo-1", "revision_seq": 1, "created_at": "2026-09-01T10:00:00+00:00", "playbook_version_id": "pv-1",
         "score": {"status": "ready", "value": 4}},
        {"memo_id": "memo-1", "revision_seq": 1, "created_at": "2026-09-30T10:00:00+00:00", "playbook_version_id": "pv-1",
         "score": {"status": "ready", "value": 8, "blocks": {}}},
    ]
    assert _client(rows).get("/api/v1/memos/memo-1/score").json()["value"] == 8
    assert _client(list(reversed(rows))).get("/api/v1/memos/memo-1/score").json()["value"] == 8


def test_a_citation_the_evidence_does_not_hold_fails_the_score_as_steps_do():
    extraction = _extraction(qualification=[_qual("presupuesto", "found", "ghost")], refs=["e1"])
    score = _score(extraction, qualification_enabled=True)
    assert score["status"] == "failed" and score["reason"] == "uncited_evidence" and score["value"] is None
    assert "blocks" in score
    assert _score(extraction) is None or _score(extraction)["status"] != "failed"  # flag off never reads it


def test_the_extraction_hook_builds_blocks_only_when_the_company_has_the_flag(monkeypatch):
    from app.services import memo_extraction_hooks as hooks

    published = []
    monkeypatch.setattr(hooks, "publish_assembled_score", lambda _sb, **kw: published.append(kw["score"]))
    extraction = _extraction(
        steps=[_step("apertura", "met", "e1")], qualification=[_qual("presupuesto", "found", "e1")], refs=["e1"],
    )

    def publish(flags):
        monkeypatch.setattr("app.services.feature_flags.is_enabled", lambda _s, _c, flag: flag in flags)
        hooks._maybe_publish_score(object(), memo=MEMO, extraction=extraction, input_revision="rev-1", patterns=[])
        return published[-1]

    assert publish({"PLAYBOOK_QUALIFICATION_ENABLED"})["blocks"]["qualification"] == {"met": 1, "applicable": 1}
    assert "blocks" not in publish(set())
