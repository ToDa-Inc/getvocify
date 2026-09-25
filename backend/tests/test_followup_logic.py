import json
import os
import unittest
from datetime import datetime, timedelta, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-followup-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-followup-32b+")

from app.services.followup_logic import (
    apply_action,
    build_messages,
    edit_ratio,
    followup_view,
    is_eligible,
    is_no_edit,
    next_voice_samples,
    parse_draft,
    should_generate,
)

NOW = datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc)
EXTRACTION = {"summary": "Resumen", "contactName": "Marina", "contactEmail": "marina@tenes.io", "contactPhone": "+34 600 111 222"}


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
