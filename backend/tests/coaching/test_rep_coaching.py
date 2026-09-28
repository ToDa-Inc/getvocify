"""Rep coaching engine: pure functions, no I/O."""

from datetime import date, datetime, timezone

from app.services.coaching.rep_coaching import (
    choose_focus,
    conversion_split,
    focus_progress,
    interaction_row,
    peer_step_medians,
    process_complete,
    step_rates,
)

STEPS = [
    {"step_id": "a", "label": "Apertura", "criterion": "c"},
    {"step_id": "b", "label": "Dolor", "criterion": "c"},
]
WEEK_START = date(2026, 9, 21)


def _memo(observations, **over):
    base = {
        "id": "m1", "user_id": "u1", "sales_motion_key": "discovery", "screening_outcome": "connected",
        "audio_duration": 120, "rep_outcome": None, "capture_started_at": "2026-09-22T10:00:00+00:00",
        "created_at": "2026-09-22T10:00:00+00:00",
        "extraction": {"summary": "# Titulo\n- Primera frase real. Otra.", "intelligence": {"playbook_observations": observations}},
    }
    base.update(over)
    return base


def _obs(step_id, status, quote=None):
    return {"step_id": step_id, "label": step_id.upper(), "criterion": "", "status": status, "quote": quote}


def _row(states, *, conv=True, meeting=False, at="2026-09-22T10:00:00+00:00", user="u1", quotes=None):
    return {
        "memo_id": "m", "user_id": user, "observed_at": at, "motion": "discovery",
        "is_conversation": conv, "meeting_agreed": meeting, "duration_s": None, "summary_line": "",
        "steps": [{"step_id": k, "label": k, "state": v, "quote": (quotes or {}).get(k)} for k, v in states.items()],
    }


def test_state_mapping_and_shape():
    row = interaction_row(_memo([_obs("a", "met", "hola"), _obs("b", "missed"), _obs("c", "unknown"), _obs("d", "not_applicable")]))
    assert [s["state"] for s in row["steps"]] == ["done", "missing", "no_evidence", "not_reached"]
    assert row["steps"][0]["quote"] == "hola"
    assert row["summary_line"] == "Primera frase real. Otra."
    assert row["observed_at"].startswith("2026-09-22T10:00:00")
    assert set(row) >= {"memo_id", "user_id", "observed_at", "motion", "is_conversation", "meeting_agreed", "duration_s"}


def test_no_observations_is_none():
    assert interaction_row(_memo([])) is None
    assert interaction_row({"id": "x", "extraction": {}}) is None


def test_summary_line_capped():
    memo = _memo([_obs("a", "met")])
    memo["extraction"]["summary"] = "x" * 400
    assert len(interaction_row(memo)["summary_line"]) == 160


def test_is_conversation_rules():
    obs = [_obs("a", "met")]
    assert interaction_row(_memo(obs))["is_conversation"] is True
    assert interaction_row(_memo(obs, screening_outcome="voicemail"))["is_conversation"] is False
    assert interaction_row(_memo(obs, screening_outcome="no_response"))["is_conversation"] is False
    assert interaction_row(_memo(obs, audio_duration=29))["is_conversation"] is False
    assert interaction_row(_memo(obs, audio_duration=30))["is_conversation"] is True
    assert interaction_row(_memo(obs, audio_duration=None))["is_conversation"] is True


def test_meeting_from_intelligence_or_rep_outcome():
    obs = [_obs("a", "met")]
    assert interaction_row(_memo(obs))["meeting_agreed"] is False
    assert interaction_row(_memo(obs, rep_outcome="meeting_booked"))["meeting_agreed"] is True
    assert interaction_row(_memo(obs, rep_outcome="other"))["meeting_agreed"] is False
    memo = _memo(obs)
    memo["extraction"]["intelligence"]["meeting"] = {"agreed": True}
    assert interaction_row(memo)["meeting_agreed"] is True


def test_step_rates_ignore_no_evidence_and_not_reached():
    rows = [_row({"a": "done", "b": "no_evidence"}), _row({"a": "missing", "b": "not_reached"}), _row({"a": "no_evidence", "b": "not_reached"})]
    a, b = step_rates(rows, STEPS)
    assert (a["done"], a["missing"], a["applicable"], a["rate"]) == (1, 1, 2, 0.5)
    assert (b["applicable"], b["rate"]) == (0, None)


def test_process_complete():
    assert process_complete(_row({"a": "done", "b": "not_reached"})) is True
    assert process_complete(_row({"a": "done", "b": "missing"})) is False
    assert process_complete(_row({"a": "no_evidence", "b": "not_reached"})) is False


def test_focus_thresholds():
    two = [_row({"a": "missing"}), _row({"a": "missing"})]
    assert choose_focus(two, STEPS) is None  # applicable < 3
    only_one_miss = [_row({"a": "done"}), _row({"a": "done"}), _row({"a": "missing"})]
    assert choose_focus(only_one_miss, STEPS) is None  # missing < 2
    ok = [_row({"a": "done"}), _row({"a": "missing"}), _row({"a": "missing"})]
    focus = choose_focus(ok, STEPS)
    assert focus["step_id"] == "a" and focus["applicable"] == 3 and focus["missing"] == 2
    assert choose_focus([], STEPS) is None


def test_focus_priority_and_tie_breaks():
    rows = [
        _row({"a": "missing", "b": "missing"}), _row({"a": "missing", "b": "missing"}),
        _row({"a": "done", "b": "done"}), _row({"a": "done", "b": "missing"}),
    ]
    # a: 2/4 = .5 ; b: 1/4 = .25 -> lowest rate wins
    assert choose_focus(rows, STEPS)["step_id"] == "b"
    tied = [_row({"a": "missing", "b": "missing"}), _row({"a": "missing", "b": "missing"}), _row({"a": "done", "b": "done"})]
    assert choose_focus(tied, STEPS)["step_id"] == "a"  # full tie -> playbook order
    # tie on rate: larger distance to the peer median wins
    assert choose_focus(tied, STEPS, {"a": 0.4, "b": 0.9})["step_id"] == "b"
    # then more applicable
    # equal rate (.5): more applicable wins
    rows = [_row({"a": "missing"}), _row({"a": "missing"}), _row({"a": "done"}), _row({"a": "done"})]
    rows += [_row({"b": "missing"})] * 3 + [_row({"b": "done"})] * 3
    assert choose_focus(rows, STEPS)["step_id"] == "b"


def test_focus_uses_previous_week_rows_only():
    prev = [_row({"a": "missing"}, at="2026-09-15T10:00:00+00:00")] * 3
    this = [_row({"a": "done"}, at="2026-09-22T10:00:00+00:00")] * 3
    assert choose_focus(prev, STEPS)["step_id"] == "a"
    assert choose_focus(this, STEPS) is None


def test_focus_progress_per_weekday_and_achieved():
    rows = [
        _row({"a": "done"}, at="2026-09-21T09:00:00+00:00"),
        _row({"a": "done"}, at="2026-09-21T15:00:00+00:00"),
        _row({"a": "missing"}, at="2026-09-23T09:00:00+00:00"),
        _row({"a": "done"}, at="2026-09-23T11:00:00+00:00"),
        _row({"a": "done"}, at="2026-09-23T12:00:00+00:00"),
        _row({"b": "done"}, at="2026-09-24T12:00:00+00:00"),
    ]
    result = focus_progress(rows, "a", WEEK_START)
    days = {d["date"]: (d["done"], d["applicable"]) for d in result["progress"]}
    assert list(days) == ["2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25"]
    assert days["2026-09-21"] == (2, 2) and days["2026-09-22"] == (0, 0) and days["2026-09-23"] == (2, 3)
    assert result["week_total"] == {"done": 4, "applicable": 5, "rate": 0.8}
    assert result["achieved"] is True


def test_focus_progress_not_achieved():
    few = focus_progress([_row({"a": "done"}), _row({"a": "done"})], "a", WEEK_START)
    assert few["achieved"] is False  # applicable < 3
    low = focus_progress([_row({"a": "done"}), _row({"a": "missing"}), _row({"a": "done"})], "a", WEEK_START)
    assert low["achieved"] is False and low["week_total"]["rate"] == 0.6667


def _conv_rows(n_complete, n_incomplete, met_c, met_i, extra=0):
    rows = []
    for i in range(n_complete):
        rows.append(_row({"a": "done"}, meeting=i < met_c))
    for i in range(n_incomplete):
        rows.append(_row({"a": "missing"}, meeting=i < met_i))
    rows += [_row({"a": "done"}, conv=False) for _ in range(extra)]
    return rows


def test_conversion_thresholds():
    ok = conversion_split(_conv_rows(15, 15, 6, 3), "sdr")
    assert ok == {"complete_rate": 0.4, "incomplete_rate": 0.2, "complete_n": 15, "incomplete_n": 15}
    assert conversion_split(_conv_rows(14, 15, 6, 3), "sdr") is None  # 29 conversations
    assert conversion_split(_conv_rows(15, 15, 6, 3, extra=20), "sdr")["complete_n"] == 15  # non-conversations excluded
    assert conversion_split(_conv_rows(4, 26, 2, 3), "sdr") is None  # group < 5
    assert conversion_split(_conv_rows(4, 4, 2, 1), "ae") is None  # 8 total but groups < 5
    assert conversion_split(_conv_rows(5, 5, 2, 1), "ae")["complete_rate"] == 0.4
    assert conversion_split(_conv_rows(5, 2, 2, 1), "ae") is None  # 7 < 8


def _people(n_people, per_person, rate_done_by_user=None):
    out = {}
    for p in range(n_people):
        done = (rate_done_by_user or {}).get(p, 1)
        rows = [_row({"a": "done" if i < done else "missing"}, user=f"u{p}") for i in range(per_person)]
        out[f"u{p}"] = rows
    return out


def test_peer_medians_thresholds():
    steps = STEPS[:1]
    assert peer_step_medians(_people(2, 20), steps) is None  # < 3 people
    assert peer_step_medians(_people(3, 9), steps) is None  # 27 conversations
    got = peer_step_medians(_people(3, 10, {0: 2, 1: 5, 2: 8}), steps)
    assert got == {"a": 0.5}
    rows = _people(3, 10)
    rows["u0"] = [_row({"a": "done"}, conv=False, user="u0")] * 10  # u0 has no conversation
    assert peer_step_medians(rows, steps) is None


def test_non_conversations_are_activity_not_evaluated():
    """Plan §8.0: voicemail / no answer / < 30 s count as activity, never against a step."""
    from app.services.coaching.rep_coaching import process_complete, step_rates

    steps = [{"step_id": "qualify", "label": "Cualificación"}]
    talk = {"is_conversation": True, "steps": [{"step_id": "qualify", "state": "done"}]}
    voicemail = {"is_conversation": False, "steps": [{"step_id": "qualify", "state": "missing"}]}
    [rate] = step_rates([talk, voicemail, voicemail], steps)
    assert (rate["done"], rate["missing"], rate["rate"]) == (1, 0, 1.0)
    assert process_complete(voicemail) is False
