from app.services.live_channel_sessions import (
    OPENING_CHECKS_S,
    RECHECK_EVERY_S,
    PcmBuffer,
    SideLanguage,
    detection_languages,
    needs_detection,
    session_language,
)


def test_spanish_streams_also_cover_english():
    assert session_language("es", ["es"]) == ("es", "bilingual-en")
    assert session_language("en", ["es", "ca"]) == ("es", "bilingual-en")
    assert session_language("en", ["en"]) == ("en", None)
    assert session_language("ca", ["es", "ca"]) == ("ca", None)


def test_checks_only_when_the_profile_has_a_language_the_start_cannot_transcribe():
    assert not needs_detection(["es"], "es", "bilingual-en")
    assert not needs_detection(["es", "en"], "es", "bilingual-en")
    assert needs_detection(["es", "ca"], "es", "bilingual-en")
    assert needs_detection(["en", "es"], "en", None)
    assert detection_languages(["es", "ca"]) == ["es", "ca", "en"]


def test_switches_only_on_a_confident_language_the_stream_does_not_cover():
    side = SideLanguage("es", "bilingual-en")
    assert side.switch_to("ca", 0.97) == "ca"
    assert side.switch_to("ca", 0.6) is None
    assert side.switch_to("en", 0.99) is None
    assert side.switch_to(None, 1.0) is None


def test_opening_checks_retry_until_sure_then_recheck_later():
    side = SideLanguage("es", "bilingual-en")
    side.add_final(0, 3)
    assert not side.due()
    side.add_final(3.5, 5)
    assert side.due()
    side.checking = True
    assert not side.due()
    side.checked(False)
    assert side.opening and side.next_check == OPENING_CHECKS_S[1]
    side.add_final(6, 12)
    side.checked(True)
    assert not side.opening
    assert side.next_check == side.speech() + RECHECK_EVERY_S


def test_window_is_the_latest_speech():
    side = SideLanguage("es", None)
    for start in range(0, 20, 2):
        side.add_final(start, start + 1.5)
    start, end = side.window()
    assert end == 19.5
    assert 19.5 - start >= 8 and start > 0


def test_restart_counts_replayed_speech_once():
    side = SideLanguage("es", "bilingual-en")
    side.add_final(1, 3)
    side.add_final(4, 6)
    side.restarted("ca", None, 3.5)
    assert side.spans == [(1, 3)]
    assert (side.language, side.domain) == ("ca", None)


def test_buffer_keeps_recent_audio_addressed_by_time():
    buf = PcmBuffer(keep_s=2)
    second = bytes(range(256)) * 125  # 1 s of s16le at 16 kHz
    for _ in range(3):
        buf.append(second)
    assert buf.start_s == 1.0
    pcm, start = buf.slice(0)
    assert start == 1.0 and len(pcm) == 64000
    pcm, start = buf.slice(2.5, 2.75)
    assert start == 2.5 and len(pcm) == 8000


def test_deepgram_unless_the_profile_has_a_language_it_cannot_transcribe(monkeypatch):
    from app.services import live_channel_sessions as live

    monkeypatch.setattr(live.settings, "DEEPGRAM_API_KEY", "key")
    assert live.live_provider([]) == "deepgram"
    assert live.live_provider(["es"]) == "deepgram"
    assert live.live_provider(["es", "en"]) == "deepgram"
    assert live.live_provider(["es", "ca"]) == "speechmatics"
    monkeypatch.setattr(live.settings, "DEEPGRAM_API_KEY", None)
    assert live.live_provider(["es"]) == "speechmatics"


def _noop(*_):
    return None


def test_deepgram_results_become_partials_finals_and_utterance_ends():
    from app.services.live_channel_sessions import DeepgramStream

    stream = DeepgramStream("rep", "es", None, vocab=[{"content": "Vocify"}], offset_s=10.0, on_event=_noop)
    assert "language=multi" in stream.url() and "keyterm=Vocify" in stream.url()
    words = [{"word": "hola", "punctuated_word": "Hola,", "start": 1.0, "end": 1.3}]
    partial = stream.events({"type": "Results", "is_final": False, "start": 1.0, "duration": 0.5,
                             "channel": {"alternatives": [{"transcript": "Hola,", "words": words}]}})
    assert partial == [{"kind": "partial", "transcript": "Hola,", "start": 11.0, "end": 11.5,
                        "words": [{"text": "Hola,", "speaker": None, "is_punct": False, "start_ms": 11000, "end_ms": 11300}]}]
    final = stream.events({"type": "Results", "is_final": True, "speech_final": True, "start": 1.0, "duration": 0.5,
                           "channel": {"alternatives": [{"transcript": "Hola."}]}})
    assert [e["kind"] for e in final] == ["final", "utterance_end"]
    assert stream.events({"type": "Metadata"}) == []


def test_speechmatics_messages_become_the_same_events():
    from app.services.live_channel_sessions import SpeechmaticsStream

    stream = SpeechmaticsStream("prospect", "es", "bilingual-en", vocab=[], offset_s=2.0, on_event=_noop)
    event = stream.events({"message": "AddTranscript", "metadata": {"transcript": "Vale.", "start_time": 1.0, "end_time": 1.4}, "results": []})
    assert event == [{"kind": "final", "transcript": "Vale.", "words": [], "start": 3.0, "end": 3.4}]
    assert stream.events({"message": "EndOfTranscript"}) == [{"kind": "done"}]
