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
)


class NormalizeSttLanguagesTest(unittest.TestCase):
    def test_defaults_and_dedupes(self):
        self.assertEqual(normalize_stt_languages(None), ["es"])
        self.assertEqual(normalize_stt_languages([]), ["es"])
        self.assertEqual(normalize_stt_languages(["ES", "es", "en", "xx"]), ["es", "en"])
        self.assertEqual(normalize_stt_languages(["ca"]), ["ca"])
        self.assertEqual(deepgram_language_code(["ca"]), "ca")

    def test_deepgram_pins_single_uses_multi_for_many(self):
        self.assertEqual(deepgram_language_code(["es"]), "es")
        self.assertEqual(deepgram_language_code(["es", "en"]), "multi")

    def test_explicit_request_beats_profile(self):
        self.assertEqual(resolve_batch_language("en"), "en")
        self.assertEqual(resolve_batch_language("auto"), "es")


if __name__ == "__main__":
    unittest.main()
