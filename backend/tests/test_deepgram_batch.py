from app.services.deepgram_batch import (
    detect_query_params,
    format_deepgram_transcript,
    language_from_deepgram_detect,
    listen_query_params,
    mean_utterance_confidence,
)


def test_multichannel_listen_skips_speaker_diarize():
    params = dict(
        listen_query_params(
            model="nova-3",
            language="es",
            keyterms=[],
            diarization=True,
            multichannel=True,
        )
    )
    assert params.get("multichannel") == "true"
    assert params.get("utterances") == "true"
    assert "diarize" not in params


def test_speaker_listen_keeps_diarize():
    params = dict(
        listen_query_params(
            model="nova-3",
            language="es",
            keyterms=[],
            diarization=True,
            multichannel=False,
        )
    )
    assert params.get("diarize") == "true"
    assert "multichannel" not in params


def test_channel_utterances_map_to_s1_s2_by_time():
    payload = {
        "results": {
            "utterances": [
                {"channel": 1, "start": 0.4, "transcript": "Dime", "confidence": 0.8},
                {"channel": 0, "start": 0.0, "transcript": "Hola", "confidence": 0.9},
                {"channel": 0, "start": 1.0, "transcript": "Soy Erik", "confidence": 0.85},
            ]
        }
    }
    text, conf = format_deepgram_transcript(payload, multichannel=True)
    assert text.splitlines() == ["S1: Hola", "S2: Dime", "S1: Soy Erik"]
    assert conf == pytest_approx_mean([0.9, 0.8, 0.85])


def test_speaker_formatter_still_uses_speaker_index():
    payload = {
        "results": {
            "utterances": [
                {"speaker": 0, "transcript": "Hola", "confidence": 0.7},
                {"speaker": 1, "transcript": "Vale", "confidence": 0.9},
            ]
        }
    }
    text, conf = format_deepgram_transcript(payload)
    assert text.splitlines() == ["S1: Hola", "S2: Vale"]
    assert conf == pytest_approx_mean([0.7, 0.9])


def test_confidence_missing_is_none():
    assert mean_utterance_confidence({"results": {"utterances": [{"transcript": "x"}]}}) is None


def test_detect_query_restricts_to_profile_languages():
    params = detect_query_params(model="nova-3", languages=["es", "ca"])
    assert params == [
        ("model", "nova-3"),
        ("detect_language", "es"),
        ("detect_language", "ca"),
    ]
    assert not any(key == "language" for key, _ in params)


def test_detect_payload_stays_inside_allowed_and_prefers_uncovered():
    payload = {
        "results": {
            "channels": [
                {"detected_language": "es"},
                {"detected_language": "ca-ES"},
            ]
        }
    }
    assert language_from_deepgram_detect(payload, ["es", "ca"], first_lang="es") == "ca"
    assert language_from_deepgram_detect(payload, ["es"], first_lang="es") == "es"
    assert language_from_deepgram_detect({"results": {"channels": [{"detected_language": "fr"}]}}, ["es", "ca"]) is None


def pytest_approx_mean(values):
    return sum(values) / len(values)
