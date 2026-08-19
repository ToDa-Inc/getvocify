"""User-profile STT language helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.services.session_entities import (
    deepgram_language_code,
    normalize_stt_languages,
    resolve_batch_language,
    speechmatics_batch_language,
)
from app.services.stt_batch import (
    _should_fallback_to_speechmatics,
    language_code_from_payload,
    should_detect_stt_language,
    should_rerun_stt,
)


class NormalizeSttLanguagesTest(unittest.TestCase):
    def test_defaults_and_dedupes(self):
        self.assertEqual(normalize_stt_languages(None), ["es"])
        self.assertEqual(normalize_stt_languages([]), ["es"])
        self.assertEqual(normalize_stt_languages(["ES", "es", "en", "xx"]), ["es", "en"])
        self.assertEqual(normalize_stt_languages(["ca"]), ["ca"])
        self.assertEqual(deepgram_language_code(["ca"]), "ca")

    def test_deepgram_pins_single_uses_multi_only_when_all_covered(self):
        self.assertEqual(deepgram_language_code(["es"]), "es")
        self.assertEqual(deepgram_language_code(["es", "en"]), "multi")
        self.assertEqual(deepgram_language_code(["fr", "de"]), "multi")
        # Nova-3 multi has no Catalan: pin the default, do not send a lying multi.
        self.assertEqual(deepgram_language_code(["ca", "es"]), "ca")
        self.assertEqual(deepgram_language_code(["es", "ca"]), "es")
        self.assertEqual(deepgram_language_code(["es", "en", "ca"]), "es")

    def test_language_code_from_payload(self):
        self.assertEqual(language_code_from_payload({"language": "ca"}, ["es", "ca"]), "ca")
        self.assertIsNone(language_code_from_payload({"language": "fr"}, ["es", "ca"]))
        self.assertIsNone(language_code_from_payload({}, ["es", "ca"]))

    def test_should_rerun_stt(self):
        allowed = ["ca", "es"]
        self.assertFalse(should_rerun_stt("es", "es", allowed))
        self.assertTrue(should_rerun_stt("es", "ca", allowed))
        self.assertTrue(should_rerun_stt("multi", "ca", allowed))
        self.assertFalse(should_rerun_stt("multi", "es", allowed))
        self.assertFalse(should_rerun_stt("es", None, allowed))
        self.assertFalse(should_rerun_stt("es", "ca", ["es"]))
        self.assertFalse(should_rerun_stt("auto", "ca", allowed))
        self.assertTrue(should_rerun_stt("ca", "es", allowed))

    def test_detect_only_when_first_pass_cannot_cover_a_selected_language(self):
        self.assertFalse(should_detect_stt_language("es", ["es"]))
        self.assertFalse(should_detect_stt_language("multi", ["es", "en"]))
        self.assertFalse(should_detect_stt_language("auto", ["ca", "es"]))
        self.assertTrue(should_detect_stt_language("es", ["es", "ca"]))
        self.assertTrue(should_detect_stt_language("ca", ["ca", "es"]))
        self.assertTrue(should_detect_stt_language("multi", ["ca", "es"]))
        self.assertFalse(
            should_detect_stt_language(deepgram_language_code(["es", "en"]), ["es", "en"])
        )
        self.assertTrue(
            should_detect_stt_language(deepgram_language_code(["es", "ca"]), ["es", "ca"])
        )
        self.assertTrue(
            should_detect_stt_language(deepgram_language_code(["ca", "es"]), ["ca", "es"])
        )

    def test_explicit_request_beats_profile(self):
        self.assertEqual(resolve_batch_language("en"), "en")
        self.assertEqual(resolve_batch_language("auto"), "es")

    def test_speechmatics_multi_uses_auto_detection(self):
        sm_lang, sm_id = speechmatics_batch_language(["ca", "es"])
        self.assertEqual(sm_lang, "auto")
        self.assertEqual(sm_id["expected_languages"], ["ca", "es"])
        self.assertEqual(sm_id["default_language"], "ca")
        single_lang, single_id = speechmatics_batch_language(["ca"])
        self.assertEqual(single_lang, "ca")
        self.assertIsNone(single_id)


class SpeechmaticsFallbackTest(unittest.TestCase):
    def test_skips_empty_audio(self):
        self.assertFalse(
            _should_fallback_to_speechmatics(RuntimeError("No audio bytes to transcribe"))
        )

    def test_falls_back_when_key_present(self):
        from unittest.mock import patch

        with patch("app.services.stt_batch._speechmatics_key_set", return_value=True):
            self.assertTrue(
                _should_fallback_to_speechmatics(RuntimeError("Deepgram listen failed (400)"))
            )
        with patch("app.services.stt_batch._speechmatics_key_set", return_value=False):
            self.assertFalse(
                _should_fallback_to_speechmatics(RuntimeError("Deepgram listen failed (400)"))
            )


if __name__ == "__main__":
    unittest.main()
