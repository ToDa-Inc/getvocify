import json
import os
import unittest
from datetime import datetime, timedelta, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-followup-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-followup-32b+")

from app.services.followup_logic import (
    PROMPT_VERSION,
    apply_action,
    build_messages,
    c04_facts,
    clean_pasted,
    edit_ratio,
    followup_view,
    is_eligible,
    is_no_edit,
    next_voice_samples,
    parse_draft,
    pasted_samples,
    should_generate,
    voice_texts,
    with_pasted,
)

NOW = datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc)
EXTRACTION = {"summary": "Resumen", "contactName": "Marina", "contactEmail": "marina@tenes.io", "contactPhone": "+34 600 111 222"}
PAIN = "Se nos quedan leads sin llamar cada semana"
C04 = {
    "pain_confirmed": True,
    "objections": [{"id": "obj-o", "quote": "Es caro", "evidence_refs": ["ev-o"]}],
    "commitments": [{
        "id": "com-a", "kind": "send", "origin": "rep_promise", "text": "Enviar la propuesta",
        "due_at": "2026-10-01T09:00:00+00:00", "temporal_precision": "time", "evidence_refs": ["ev-a"],
    }],
    "meeting": {"agreed": True, "starts_at": "2026-10-02T09:30:00+00:00", "timezone": None,
                "precision": "time", "evidence_refs": ["ev-m"]},
    "evidence": [
        {"id": "ev-p", "quote": PAIN},
        {"id": "ev-o", "quote": "Es caro"},
        {"id": "ev-a", "quote": "Te mando la propuesta el jueves a las once"},
        {"id": "ev-m", "quote": "El viernes a las once y media"},
    ],
}


def pasted(text):
    return {"text": text, "source": "pasted"}


class Eligibility(unittest.TestCase):
    def test_real_conversations_only(self):
        memo = {"transcript": "Marina: hola", "extraction": EXTRACTION, "screening_outcome": None}
        self.assertTrue(is_eligible(memo))
        self.assertFalse(is_eligible({**memo, "screening_outcome": "voicemail"}))
        self.assertFalse(is_eligible({**memo, "transcript": "  "}))
        self.assertFalse(is_eligible({**memo, "extraction": {"summary": ""}}))

    def test_single_flight_decision(self):
        self.assertTrue(should_generate(None, NOW))
        fresh = {"status": "generating", "started_at": (NOW - timedelta(seconds=30)).isoformat()}
        stale = {"status": "generating", "started_at": (NOW - timedelta(minutes=5)).isoformat()}
        self.assertFalse(should_generate(fresh, NOW))
        self.assertTrue(should_generate(stale, NOW))
        for status in ("ready", "sent", "unavailable"):
            self.assertFalse(should_generate({"status": status}, NOW))


class Drafting(unittest.TestCase):
    def test_parse_draft(self):
        self.assertEqual(parse_draft({"subject": "  Caso   de logística ", "body": " Hola ", "language": "es"}),
                         {"subject": "Caso de logística", "body": "Hola", "language": "es"})
        self.assertIsNone(parse_draft({"subject": "x", "body": " "}))
        self.assertIsNone(parse_draft("not json"))
        self.assertEqual(len(parse_draft({"subject": "s" * 500, "body": "b"})["subject"]), 160)

    def test_messages_carry_context_and_last_three_samples(self):
        msgs = build_messages(system_prompt="SYS", transcript="Marina: hola", summary="Resumen", next_steps=["Enviar caso"],
                              contact_name="Marina", rep_name="Lucía", voice_samples=["1", "2", "3", "4"])
        self.assertEqual(msgs[0], {"role": "system", "content": "SYS"})
        ctx = json.loads(msgs[1]["content"])
        self.assertEqual(ctx["voice_samples"], ["2", "3", "4"])
        self.assertIn("Lucía", msgs[1]["content"], "accents survive (ensure_ascii=False)")

    def test_without_c04_the_input_is_exactly_todays(self):
        kwargs = dict(system_prompt="SYS", transcript="Marina: hola", summary="Resumen", next_steps=["Enviar caso"],
                      contact_name="Marina", rep_name="Lucía", voice_samples=["a"])
        today = {"rep_name": "Lucía", "contact_name": "Marina", "summary": "Resumen", "next_steps": ["Enviar caso"],
                 "voice_samples": ["a"], "transcript": "Marina: hola"}
        self.assertEqual(build_messages(**kwargs)[1]["content"], json.dumps(today, ensure_ascii=False))
        self.assertEqual(build_messages(**kwargs, facts=None)[1]["content"], json.dumps(today, ensure_ascii=False))

    def test_c04_facts_follow_next_steps_in_the_input(self):
        facts = {"commitments": [{"text": "Enviar la propuesta"}], "meeting": None, "pain_quote": PAIN}
        msgs = build_messages(system_prompt="SYS", transcript="t", summary="s", next_steps=["n"],
                              contact_name="Marina", rep_name="Lucía", voice_samples=[], facts=facts)
        ctx = json.loads(msgs[1]["content"])
        self.assertEqual(list(ctx), ["rep_name", "contact_name", "summary", "next_steps", "commitments", "meeting",
                                     "pain_quote", "voice_samples", "transcript"])
        self.assertEqual((ctx["commitments"], ctx["meeting"], ctx["pain_quote"]), (facts["commitments"], None, PAIN))

    def test_prompt_is_versioned(self):
        self.assertEqual(PROMPT_VERSION, "followup_v2")


class C04Facts(unittest.TestCase):
    def test_commitments_meeting_and_pain_in_the_rep_timezone(self):
        facts = c04_facts(C04, "Europe/Madrid")
        self.assertEqual(facts, {
            "commitments": [{"text": "Enviar la propuesta", "day": "Thursday 2026-10-01", "time": "11:00"}],
            "meeting": {"day": "Friday 2026-10-02", "time": "11:30"},
            "pain_quote": PAIN,
        })

    def test_meeting_with_only_a_day_has_no_time(self):
        block = {**C04, "meeting": {"agreed": True, "starts_at": "2026-10-02", "precision": "date", "evidence_refs": ["ev-m"]}}
        self.assertEqual(c04_facts(block, "Europe/Madrid")["meeting"], {"day": "Friday 2026-10-02"})

    def test_commitment_with_only_a_day_keeps_its_day_in_any_zone(self):
        day_only = {**C04["commitments"][0], "due_at": "2026-10-01T00:00:00+02:00", "temporal_precision": "date"}
        facts = c04_facts({**C04, "commitments": [day_only]}, "America/New_York")
        self.assertEqual(facts["commitments"], [{"text": "Enviar la propuesta", "day": "Thursday 2026-10-01"}])

    def test_undated_commitment_is_only_text(self):
        undated = {**C04["commitments"][0], "due_at": None, "temporal_precision": "unknown"}
        self.assertEqual(c04_facts({**C04, "commitments": [undated]}, "Europe/Madrid")["commitments"],
                         [{"text": "Enviar la propuesta"}])

    def test_meeting_not_agreed_or_without_a_date_is_null(self):
        for meeting in (
            {"agreed": False, "starts_at": None, "precision": "unknown", "evidence_refs": ["ev-m"]},
            {"agreed": True, "starts_at": None, "precision": "unknown", "evidence_refs": ["ev-m"]},
            {"agreed": None, "starts_at": None, "precision": "unknown", "evidence_refs": []},
            None,
        ):
            self.assertIsNone(c04_facts({**C04, "meeting": meeting}, "Europe/Madrid")["meeting"], meeting)

    def test_pain_quote_only_when_pain_is_confirmed(self):
        self.assertIsNone(c04_facts({**C04, "pain_confirmed": False}, "Europe/Madrid")["pain_quote"])
        self.assertIsNone(c04_facts({**C04, "pain_confirmed": None}, "Europe/Madrid")["pain_quote"])

    def test_another_rep_timezone_moves_day_and_time(self):
        facts = c04_facts(C04, "Atlantic/Canary")
        self.assertEqual(facts["commitments"][0]["time"], "10:00")
        self.assertEqual(facts["meeting"], {"day": "Friday 2026-10-02", "time": "10:30"})
        self.assertEqual(c04_facts(C04, "Not/AZone")["meeting"]["time"], "11:30", "unknown zone falls back to Madrid")


class PastedSamples(unittest.TestCase):
    def test_clean_trims_skips_blanks_and_enforces_limits(self):
        ok = "Hola Marina, te paso lo que hablamos esta mañana."
        self.assertEqual(clean_pasted([f"  {ok}  ", "", "   "]), [ok])
        self.assertEqual(clean_pasted([]), [])
        self.assertEqual(len(clean_pasted(["a" * 40, "b" * 1500])), 2)
        for bad in ([ok] * 4, ["a" * 39], ["a" * 1501]):
            with self.assertRaises(ValueError):
                clean_pasted(bad)

    def test_saving_replaces_pasted_and_keeps_learned(self):
        stored = ["l1", pasted("old"), "l2"]
        self.assertEqual(with_pasted(stored, ["p1", "p2"]), ["l1", "l2", pasted("p1"), pasted("p2")])
        self.assertEqual(pasted_samples(with_pasted(stored, ["p1"])), ["p1"])

    def test_emptying_removes_pasted_only(self):
        self.assertEqual(with_pasted(["l1", pasted("old"), "l2"], []), ["l1", "l2"])

    def test_edits_never_evict_pasted_samples(self):
        stored = [pasted("p1")] + [f"l{i}" for i in range(5)]
        self.assertEqual(next_voice_samples(stored, "new", 0.3), [pasted("p1"), "l1", "l2", "l3", "l4", "new"])

    def test_the_prompt_reads_texts_in_order(self):
        self.assertEqual(voice_texts(["l1", pasted("p1"), 5, {"bad": 1}, pasted("  "), "l2"]), ["l1", "p1", "l2"])


class Metrics(unittest.TestCase):
    def test_edit_ratio_and_no_edit(self):
        draft = "Hola Marina, gracias por el rato de hoy. Te paso el caso de logística."
        self.assertEqual(edit_ratio(draft, draft.replace(" ", "  ")), 0.0)
        self.assertTrue(is_no_edit(edit_ratio(draft, draft.replace("rato", "ratoo"))))
        self.assertGreater(edit_ratio(draft, "Marina, adjunto propuesta. Un saludo."), 0.5)

    def test_voice_samples_only_learn_from_real_edits(self):
        self.assertEqual(next_voice_samples(["a"], "body", 0.0), ["a"])
        self.assertEqual(next_voice_samples(["a"], " mine ", 0.3), ["a", "mine"])
        self.assertEqual(next_voice_samples([str(i) for i in range(5)], "new", 0.3), ["1", "2", "3", "4", "new"])

    def test_apply_action_records_hand_off_and_edit_ratio(self):
        current = {"status": "ready", "subject": "Caso", "body": "Hola Marina, te paso el caso."}
        sent = apply_action(current, action="sent", channel="email", subject="", body="Hola Marina, te paso el caso.", now=NOW)
        self.assertEqual((sent["status"], sent["channel"], sent["final_subject"], sent["no_edit"]), ("sent", "email", "Caso", True))
        copied = apply_action(current, action="copied", channel="email", subject="Caso", body="Otra cosa distinta.", now=NOW)
        self.assertEqual(copied["status"], "ready", "copying is not sending")
        self.assertFalse(copied["no_edit"])
        with self.assertRaises(ValueError):
            apply_action(current, action="deleted", channel="email", subject="", body="x", now=NOW)


class View(unittest.TestCase):
    def test_view_per_status(self):
        memo = {"extraction": EXTRACTION}
        self.assertEqual(followup_view(memo), {"status": "unavailable", "recipientName": "Marina"})
        self.assertEqual(followup_view(memo, scheduled=True)["status"], "generating")
        ready = followup_view({**memo, "followup": {"status": "ready", "subject": "S", "body": "B"}})
        self.assertEqual((ready["to"], ready["phone"], ready["subject"]), ("marina@tenes.io", "+34600111222", "S"))
        sent = followup_view({**memo, "followup": {"status": "sent", "subject": "S", "body": "B", "final_body": "B2", "channel": "whatsapp"}})
        self.assertEqual((sent["body"], sent["channel"]), ("B2", "whatsapp"))

    def test_phone_without_country_code_is_not_offered_for_whatsapp(self):
        view = followup_view({"extraction": {**EXTRACTION, "contactPhone": "600111222"}, "followup": {"status": "ready", "subject": "S", "body": "B"}})
        self.assertNotIn("phone", view)


if __name__ == "__main__":
    unittest.main()
