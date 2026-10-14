"""REPORT_FEEDBACK_ENABLED: the rep's and the Head of Sales' numbers (rep_digest), the written feedback
(feedback_writer) and their email (digest_email)."""

import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-report-feedback-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-report-feedback-32")

import pytest

from app.services.reporting import feedback_writer, rep_digest
from app.services.reporting.presentation import email_html_for_snapshot, email_subject

DAY = datetime(2026, 10, 13, 22, 0, tzinfo=timezone.utc)  # Tuesday 00:00 Madrid
START, END = DAY, DAY + timedelta(days=1)
PREVIOUS = DAY - timedelta(days=1)
STEPS = [
    {"step_id": "apertura", "label": "Apertura"},
    {"step_id": "datos", "label": "Datos de la empresa"},
]


def _memo(memo_id, at, *, screening="connected", seconds=120, kind="call", statuses=None, outcome=None, objections=None):
    observations = [
        {"step_id": key, "label": "Apertura" if key == "apertura" else "Datos de la empresa", "status": status,
         "quote": f"cita {memo_id}", "reason": "No preguntaste ningún dato.", "advice": "Pregunta el ticket medio."}
        for key, status in (statuses or {}).items()
    ]
    return {
        "id": memo_id, "user_id": "rep-1", "sales_motion_key": "discovery", "screening_outcome": screening,
        "audio_duration": seconds, "interaction_kind": kind, "created_at": at.isoformat(), "rep_outcome": outcome,
        "extraction": {"intelligence": {"playbook_observations": observations, "objections": objections or []}},
    }


def _playbook(_motion):
    return {"published": True, "steps": STEPS, "entries": [{"entry_id": "objection:price", "category": "price", "guidance": "Lo comparamos."}]}


def test_activity_counts_calls_conversations_and_the_previous_day():
    memos = [
        _memo("a", START + timedelta(hours=9), statuses={"apertura": "met"}),
        _memo("b", START + timedelta(hours=10), screening="voicemail"),
        _memo("c", START + timedelta(hours=11), seconds=10),  # too short to be a conversation
        _memo("d", START + timedelta(hours=12), statuses={"apertura": "met"}, outcome="meeting_booked"),
        _memo("e", PREVIOUS + timedelta(hours=9), statuses={"apertura": "met"}),
        _memo("f", START + timedelta(hours=13), kind="meeting", seconds=1800, statuses={"apertura": "met"}),
    ]
    found = rep_digest.digest(memos, start=START, end=END, previous_start=PREVIOUS, playbook_for=_playbook,
                              labels={"discovery": "Llamada en frío"}, sales_role="sdr")
    act = found["activity"]
    assert (act["calls"], act["conversations"], act["no_answer"], act["meetings_held"]) == (4, 3, 1, 1)
    assert act["meetings_booked"] == 1 and act["talk_minutes"] == 34
    assert act["connect_rate"] == 0.5  # 2 call conversations of 4 calls
    assert found["previous"]["calls"] == 1 and found["previous"]["connect_rate"] is None  # 1 call: no rate


def test_no_declared_outcome_is_unknown_not_zero():
    memos = [_memo(m, START + timedelta(hours=h), statuses={"apertura": "met"}) for m, h in (("a", 9), ("b", 10), ("c", 11))]
    act = rep_digest.activity(memos, START, END)
    assert act["meetings_booked"] is None and act["booking_rate"] is None


def test_coaching_gives_the_process_strengths_slips_and_objections():
    price = [{"kind": "objection", "category": "price", "resolution": "open", "quote": "es caro", "response": None}]
    memos = [
        _memo("a", START + timedelta(hours=9), statuses={"apertura": "met", "datos": "missed"}, objections=price),
        _memo("b", START + timedelta(hours=10), statuses={"apertura": "met", "datos": "missed"}),
        _memo("c", START + timedelta(hours=11), statuses={"apertura": "met", "datos": "met"}),
    ]
    coach = rep_digest.coaching(memos, START, END, _playbook, {"discovery": "Llamada en frío"})
    assert coach["evaluated"] == 3 and coach["by_type"] == {"Llamada en frío": 3}
    assert coach["adherence_steps"] == {"met": 4, "applicable": 6} and round(coach["adherence"], 3) == 0.667
    assert coach["strengths"][0]["label"] == "Apertura" and coach["strengths"][0]["times"] == 3
    assert coach["slips"][0]["label"] == "Datos de la empresa" and coach["slips"][0]["missing"] == 2
    assert coach["slips"][0]["advice"] == "Pregunta el ticket medio."
    assert coach["objections"] == [{"label": "Precio", "total": 1, "open": 1, "resolved": 0, "quote": "es caro",
                                    "response": None, "playbook_answer": "Lo comparamos."}]


def test_fewer_than_three_conversations_give_no_process_rate():
    memos = [_memo("a", START + timedelta(hours=9), statuses={"apertura": "met"})]
    assert rep_digest.coaching(memos, START, END, _playbook, {})["adherence"] is None


class _LLM:
    def __init__(self, answer):
        self.answer, self.calls = answer, 0

    async def chat_json(self, messages, **kwargs):
        self.calls += 1
        return self.answer


ANSWER = {"headline": "12 llamadas y 5 conversaciones.", "went_well": ["Abriste bien."], "to_improve": ["Pide datos."],
          "focus": "Datos de la empresa.", "people": [{"name": "Ana", "note": "Bien."}, {"name": "Intrusa", "note": "x"}]}


@pytest.fixture
def flag_on(monkeypatch):
    monkeypatch.setattr(feedback_writer, "is_enabled", lambda *a, **k: True)


def _payload(audience="rep", calls=12, reps=None):
    facts = {"activity": {"calls": calls, "meetings_held": 0}, "coaching": {"evaluated": 5}}
    if reps is not None:
        facts["reps"] = reps
    return {"audience": audience, "period": "day", "sales_role": "sdr", "facts": facts}


def test_feedback_is_written_once_per_set_of_facts(flag_on):
    llm = _LLM(ANSWER)
    first = feedback_writer.write_feedback(object(), company_id="co", payload=_payload(), llm=llm)
    assert first["headline"] == "12 llamadas y 5 conversaciones." and first["went_well"] == ["Abriste bien."]
    assert "people" not in first
    again = feedback_writer.write_feedback(object(), company_id="co", payload=_payload(), previous=first, llm=llm)
    assert again is first and llm.calls == 1  # same facts: no second model call
    feedback_writer.write_feedback(object(), company_id="co", payload=_payload(calls=13), previous=first, llm=llm)
    assert llm.calls == 2


def test_head_of_sales_notes_only_about_reps_in_the_facts(flag_on):
    shaped = feedback_writer.write_feedback(
        object(), company_id="co", payload=_payload("head_of_sales", reps=[{"name": "Ana"}]), llm=_LLM(ANSWER),
    )
    assert shaped["people"] == [{"name": "Ana", "note": "Bien."}]


def test_no_feedback_when_off_without_activity_or_on_a_bad_answer(monkeypatch, flag_on):
    assert feedback_writer.write_feedback(object(), company_id="co", payload=_payload(calls=0), llm=_LLM(ANSWER)) is None
    assert feedback_writer.write_feedback(object(), company_id="co", payload=_payload(), llm=_LLM({"went_well": []})) is None

    class Boom(_LLM):
        async def chat_json(self, messages, **kwargs):
            raise RuntimeError("model down")

    assert feedback_writer.write_feedback(object(), company_id="co", payload=_payload(), llm=Boom(None)) is None
    monkeypatch.setattr(feedback_writer, "is_enabled", lambda *a, **k: False)
    assert feedback_writer.write_feedback(object(), company_id="co", payload=_payload(), llm=_LLM(ANSWER)) is None


def _snapshot(scope="self", report_type="daily"):
    activity = {"calls": 31, "conversations": 17, "no_answer": 12, "meetings_held": 0, "meetings_booked": None,
                "talk_minutes": 36, "connect_rate": 0.5484, "booking_rate": None}
    digest = {
        "sales_role": "sdr", "activity": activity, "previous": {**activity, "calls": 20, "conversations": 17},
        "coaching": {"evaluated": 17, "adherence": 0.71, "adherence_steps": {"met": 35, "applicable": 49},
                     "by_type": {"Llamada en frío": 15}, "strengths": [], "slips": [],
                     "objections": [{"label": "Precio <b>", "total": 3, "open": 3, "resolved": 0}]},
    }
    if scope == "team":
        digest["reps"] = [{"name": "Álvaro", "sales_role": "sdr", "calls": 31, "conversations": 17, "meetings_held": 0,
                           "meetings_booked": None, "adherence": 0.71, "evaluated": 17, "top_slip": "Datos"}]
    return {"scope": scope, "report_type": report_type, "metrics": {}, "digest": digest,
            "feedback": {"headline": "Buen día <script>", "went_well": ["Conectaste en 17 de 31."], "to_improve": ["Pide datos."],
                         "focus": "Datos de la empresa.", "people": [{"name": "Álvaro", "note": "Trabaja los datos."}]}}


def test_email_shows_numbers_change_feedback_and_escapes():
    html = email_html_for_snapshot(_snapshot(), report_id="r1", app_origin="https://app.example.com")
    assert "Buen día &lt;script&gt;" in html and "<script>" not in html and "Precio &lt;b&gt;" in html
    assert "+11 vs el día anterior" in html and "55 % de conexión" in html and "Sin marcar" in html
    assert "Lo que salió bien" in html and "Qué mejorar" in html and "Tu foco" in html
    assert "35 de 49 pasos" in html and "https://app.example.com/dashboard/reports/r1" in html
    assert email_subject(_snapshot()) == "Tu día en Vocify: 31 llamadas, 17 conversaciones"


def test_team_email_has_one_card_per_rep_with_their_note():
    snapshot = _snapshot("team", "weekly")
    html = email_html_for_snapshot(snapshot, report_id="r2")
    assert "Por comercial" in html and "Álvaro" in html and "Trabaja los datos." in html
    assert "reuniones sin marcar" in html and "+11 vs la semana pasada" in html
    assert email_subject(snapshot) == "Tu equipo esta semana: 31 llamadas, 17 conversaciones"


def test_a_report_without_digest_keeps_the_old_email():
    snapshot = {"scope": "self", "metrics": {"attempts": 2, "connected_calls": 1, "meetings_agreed": 0}, "coaching": None}
    assert "Ver informe" in email_html_for_snapshot(snapshot, report_id="r3")
    assert email_subject(snapshot) == "Tu resumen de actividad"
