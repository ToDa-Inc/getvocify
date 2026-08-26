"""Cheap sanitize before extract; LLM polish is display-only and must not block."""

import unittest

from app.services.transcript_sanitize import (
    collapse_extra_speakers,
    extraction_complete_update,
    raw_speaker_count,
    reconstruct_spelled_emails,
    should_refresh_display_transcript,
)


class DisplayTranscriptPolishTests(unittest.TestCase):
    def test_review_statuses_can_receive_polished_transcript(self):
        self.assertTrue(should_refresh_display_transcript("extracting"))
        self.assertTrue(should_refresh_display_transcript("pending_review"))
        self.assertTrue(should_refresh_display_transcript("pending_transcript"))

    def test_approved_or_failed_transcript_is_not_replaced(self):
        self.assertFalse(should_refresh_display_transcript("approved"))
        self.assertFalse(should_refresh_display_transcript("failed"))
        self.assertFalse(should_refresh_display_transcript(None))

    def test_extraction_persist_does_not_clobber_transcript(self):
        """Extract finishes while LLM polish may already have written a better transcript."""
        payload = extraction_complete_update(
            {"summary": "note"},
            processed_at="2026-08-21T12:00:00+00:00",
        )
        self.assertNotIn("transcript", payload)
        self.assertEqual(payload["status"], "pending_review")
        self.assertEqual(payload["extraction"]["summary"], "note")
        self.assertIsNone(payload["processing_started_at"])


class TwoPartySpeakerCollapseTests(unittest.TestCase):
    def test_folds_third_speaker_into_two_parties(self):
        src = (
            "SPEAKER: S1\nHola, soy Dani de Vocify, te llamo por el concurso y el seguimiento.\n\n"
            "SPEAKER: S2\nSí, dime, estamos en ello y te confirmo fechas la semana que viene.\n\n"
            "SPEAKER: S3\nEl jueves de la semana del 24.\n\n"
            "SPEAKER: S1\nPerfecto, lo apunto y te escribo.\n"
        )
        self.assertEqual(raw_speaker_count(src), 3)
        out = collapse_extra_speakers(src)
        self.assertEqual(raw_speaker_count(out), 2)
        self.assertIn("El jueves de la semana del 24", out)
        self.assertNotRegex(out, r"\bS3\b")


class SpelledEmailReconstructionTests(unittest.TestCase):
    def test_spanish_letter_by_letter_gmail(self):
        src = "DE, A, ENE, I, ARROBA GMAIL PUNTO COM"
        self.assertIn("dani@gmail.com", reconstruct_spelled_emails(src, "es"))

    def test_spanish_v_is_uve_never_be(self):
        uve = reconstruct_spelled_emails(
            "JOTA, A, UVE, I, E, ERRE, PUNTO, UVE, A, ELE, ELE, E, ARROBA GMAIL PUNTO COM",
            "es",
        )
        self.assertIn("javier.valle@gmail.com", uve)
        be = reconstruct_spelled_emails("BE, E, ARROBA GMAIL PUNTO COM", "es")
        self.assertIn("be@gmail.com", be)
        self.assertNotIn("ve@gmail.com", be)

    def test_initial_plus_lastname_across_speaker_gap(self):
        src = (
            "el correo es f Gallardo.\n\n"
            "SPEAKER: S2\n"
            "Ok. Arroba Ascale punto es, imagínate. Arroba Ascale punto es."
        )
        out = reconstruct_spelled_emails(src, "es")
        self.assertIn("fgallardo@ascale.es", out)
        self.assertNotIn("imaginate@ascale.es", out)

    def test_english_at_dot(self):
        src = "DEE AY EN EYE AT GMAIL DOT COM"
        self.assertIn("dani@gmail.com", reconstruct_spelled_emails(src, "en"))


if __name__ == "__main__":
    unittest.main()
