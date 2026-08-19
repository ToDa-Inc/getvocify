"""Speechmatics batch config from the file-STT bake-off."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.services.speechmatics_batch import BATCH_OPERATING_POINT, batch_transcription_config


class SpeechmaticsBatchConfigTest(unittest.TestCase):
    def test_standard_pinned_language_vocab_and_diarize(self):
        cfg = batch_transcription_config(
            language="es",
            diarization=True,
            vocab=[{"content": "Vocify"}],
        )
        self.assertEqual(BATCH_OPERATING_POINT, "standard")
        self.assertEqual(cfg["operating_point"], "standard")
        self.assertEqual(cfg["language"], "es")
        self.assertEqual(cfg["diarization"], "speaker")
        self.assertEqual(cfg["additional_vocab"], [{"content": "Vocify"}])
        self.assertNotIn("max_speakers", cfg)


if __name__ == "__main__":
    unittest.main()
