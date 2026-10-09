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


def test_upsampler_turns_16k_into_24k_without_gaps_between_chunks():
    from array import array
    from app.services.live_channel_sessions import Upsampler

    up = Upsampler()
    ramp = array("h", range(0, 3200, 2))  # 1600 samples
    first = array("h"); first.frombytes(up(ramp.tobytes()))
    assert len(first) == 2399  # the last input sample waits for the next chunk
    second = array("h"); second.frombytes(up(array("h", range(3200, 6400, 2)).tobytes()))
    assert len(second) == 2400
    joined = list(first) + list(second)
    steps = {b - a for a, b in zip(joined, joined[1:])}
    assert steps <= {1, 2}  # a steady ramp: no jump at the chunk edge


def test_mai_deltas_settle_whole_words_and_partials_show_the_rest():
    from app.services.live_channel_sessions import MaiStream

    stream = MaiStream("rep", "es", None, vocab=[], offset_s=10.0, on_event=_noop)
    assert stream.subprotocols("k") == ["ai-gateway-transcription.v1", "ai-gateway-auth.k"]
    stream.feed(b"\0" * 32000)
    texts = lambda events: [(e["kind"], e["transcript"]) for e in events]
    assert texts(stream.events({"type": "transcript-delta", "delta": " No sé si te acuer"})) == [("final", "No sé si te")]
    # The held half word leads the changing end.
    assert texts(stream.events({"type": "transcript-partial", "text": "das de mí."})) == [("partial", "acuerdas de mí.")]
    assert texts(stream.events({"type": "transcript-delta", "delta": "das de"})) == [("final", "acuerdas")]
    assert texts(stream.events({"type": "transcript-delta", "delta": " mí."})) == [("final", "de mí.")]
    assert texts(stream.events({"type": "transcript-delta", "delta": ","})) == [("final", ",")]
    # No times from MAI: a sentence spans from the last one to the audio fed so far.
    first = MaiStream("rep", "es", None, vocab=[], offset_s=10.0, on_event=_noop)
    first.feed(b"\0" * 32000)
    event = first.events({"type": "transcript-delta", "delta": "Hola."})[0]
    assert (event["start"], event["end"], event["timed"]) == (10.0, 11.0, False)
    held = MaiStream("rep", "es", None, vocab=[], offset_s=0.0, on_event=_noop)
    assert texts(held.events({"type": "transcript-delta", "delta": " hasta luego"})) == [("final", "hasta")]
    done = held.events({"type": "finish", "text": "", "segments": []})
    assert [(e["kind"], e.get("transcript")) for e in done] == [("final", "luego"), ("done", None)]
    assert MaiStream("rep", "es", None, vocab=[], offset_s=0.0, on_event=_noop).events(
        {"type": "error", "error": {"name": "X", "message": "nope"}}) == [{"kind": "error", "reason": "nope"}]


def test_glossary_fixes_listed_sound_alikes_and_nothing_else():
    from app.services.live_channel_sessions import apply_glossary, glossary_terms

    terms = glossary_terms([{"content": "Vocify", "sounds_like": ["Vosify", "Voiceify"]}, {"content": "Cobee", "sounds_like": ["Kobi"]}, {"content": "HubSpot"}])
    assert apply_glossary("oye, Vosify, están con Kobi y hubspot", terms) == "oye, Vocify, están con Cobee y HubSpot"
    assert apply_glossary("Voiceify-ify", terms) == "Vocify-ify"  # whole words only, punctuation is a boundary
    assert apply_glossary("Sofía dijo que sí", terms) == "Sofía dijo que sí"  # resembling is not enough
    assert apply_glossary("Kobiyashi", terms) == "Kobiyashi"
    assert apply_glossary("hola", []) == "hola"


def test_words_that_sound_like_a_term_take_its_spelling():
    from app.services.live_channel_sessions import apply_glossary, glossary_sounds, glossary_terms, sound_key

    assert {sound_key(w) for w in ("Cobee", "Cobi", "Covi", "Koby", "Kobi")} == {"kobi"}
    assert sound_key("Vosify") == sound_key("Vocify")
    terms = glossary_terms([{"content": "Cobee", "sounds_like": ["Cobi", "Covi"]}, {"content": "Vocify"}, {"content": "Vale"}, {"content": "Piper AI"}])
    sounds = glossary_sounds(terms)
    assert apply_glossary("están con Koby y con Vosify", terms, sounds) == "están con Cobee y con Vocify"
    # An everyday word is never taken for a term that sounds like it.
    assert apply_glossary("bale, perfecto", terms, sounds) == "bale, perfecto"
    assert apply_glossary("Sofía y Kobiyashi", terms, sounds) == "Sofía y Kobiyashi"
    # Two terms that sound alike: neither is guessed.
    clash = glossary_terms([{"content": "Kobi"}, {"content": "Cobee"}])
    assert glossary_sounds(clash) == {}


def test_mai_sends_speech_with_a_little_before_and_after_and_holds_silence():
    from array import array
    from app.services.live_channel_sessions import MaiStream

    stream = MaiStream("prospect", "es", None, vocab=[], offset_s=0.0, on_event=_noop)
    quiet = bytes(3200)  # 100 ms of silence
    voice = array("h", [3000, -3000] * 800).tobytes()  # 100 ms, clearly speech
    for _ in range(20):
        stream.feed(quiet)
    assert stream.fed_s == 0.0 and round(stream.heard_s, 1) == 2.0
    stream.feed(voice)  # 0.3 s held before it go out with it
    assert round(stream.fed_s, 1) == 0.4
    for _ in range(20):
        stream.feed(quiet)
    # 0.6 s after the voice still go, then nothing.
    assert round(stream.fed_s, 1) == 1.0
    assert stream.billed_seconds() == stream.fed_s
    # Times still follow everything heard, silence included.
    assert round(stream.heard_s, 1) == 4.1


def test_mai_hears_the_quiet_after_speech_until_it_settles_the_last_words():
    from array import array
    from app.services.live_channel_sessions import HANG_S, PRE_ROLL_S, SETTLE_TAIL_S, MaiStream

    quiet = bytes(3200)  # 100 ms
    voice = array("h", [3000, -3000] * 800).tobytes()
    stream = MaiStream("prospect", "es", None, vocab=[], offset_s=0.0, on_event=_noop)
    stream.feed(voice)
    stream.events({"type": "transcript-delta", "delta": " es"})
    stream.events({"type": "transcript-partial", "text": " más que suficiente."})
    for _ in range(10):
        stream.feed(quiet)
    # The hang, then the quiet keeps going while words are still unsettled.
    assert round(stream.fed_s, 1) == 1.1
    stream.events({"type": "transcript-delta", "delta": " más que suficiente."})  # no partial after it: all settled
    for _ in range(10):
        stream.feed(quiet)
    assert round(stream.fed_s, 1) == 1.1

    # MAI never settles: the quiet stops at the cap.
    stuck = MaiStream("prospect", "es", None, vocab=[], offset_s=0.0, on_event=_noop)
    stuck.feed(voice)
    stuck.events({"type": "transcript-partial", "text": " y luego"})
    for _ in range(int((HANG_S + SETTLE_TAIL_S) * 10) + 30):
        stuck.feed(quiet)
    assert round(stuck.fed_s, 1) == round(0.1 + HANG_S + SETTLE_TAIL_S, 1)
    # Speech again goes out with the moment before it, and starts a fresh tail.
    stuck.feed(voice)
    assert round(stuck.fed_s, 1) == round(0.2 + HANG_S + SETTLE_TAIL_S + PRE_ROLL_S, 1)
    assert stuck.tail_s == 0.0


def test_a_quiet_side_still_keeps_its_session_alive():
    from app.services.live_channel_sessions import KEEPALIVE_S, MaiStream

    stream = MaiStream("prospect", "es", None, vocab=[], offset_s=0.0, on_event=_noop)
    for _ in range(int(KEEPALIVE_S * 10) + 1):
        stream.feed(bytes(3200))
    assert round(stream.fed_s, 1) == 0.1


class _FakeStream:
    """A provider stream the test drives: it records what it is given and starts (or not) as told."""

    starts = True
    made: list = []

    def __init__(self, label, language, domain, *, vocab, offset_s, on_event):
        import asyncio

        self.label, self.language, self.domain, self.offset_s, self.on_event = label, language, domain, offset_s, on_event
        self.provider = "mai"
        self.ready = asyncio.Event()
        self.finished = asyncio.Event()
        self.started_at = None
        self.live_from_s = 0.0
        self.task = None
        self.fed = bytearray()
        self.ended = False
        _FakeStream.made.append(self)

    def start(self, api_key):
        if _FakeStream.starts:
            self.started_at = 1.0
            self.ready.set()

    def feed(self, pcm):
        self.fed.extend(pcm)

    def end(self):
        self.ended = True


class _FakeClient:
    def __init__(self):
        self.sent = []

    async def send_json(self, payload):
        self.sent.append(payload)


def _sessions(monkeypatch):
    from app.services import live_channel_sessions as live

    monkeypatch.setattr(live.settings, "AI_GATEWAY_API_KEY", "k")
    monkeypatch.setattr(live.settings, "LIVE_STT_PROVIDER", "mai")
    monkeypatch.setitem(live.STREAMS, "mai", _FakeStream)
    monkeypatch.setattr(live, "RECOVER_BACKOFF_S", (0.0,))
    monkeypatch.setattr(live, "FINISH_TIMEOUT_S", 0.05)
    _FakeStream.made = []
    _FakeStream.starts = True
    client = _FakeClient()
    sessions = live.ChannelSessions(client, labels=["prospect", "rep"], language="multi", profile_languages=["es"], glossary=[], detect=False)
    return live, sessions, client


def test_a_side_whose_stream_dies_mid_call_is_reopened_and_its_unsettled_audio_replayed(monkeypatch):
    import asyncio

    live, sessions, client = _sessions(monkeypatch)

    async def scenario():
        failed = sessions._open("rep", "es", "bilingual-en", offset_s=0.0)
        sessions.active["rep"] = failed
        # 10 s of the rep's audio heard, the last words settled at 6.0 s.
        sessions.buffers["rep"].append(bytes(10 * live.BYTES_PER_SECOND))
        sessions.sides["rep"].add_final(2.0, 6.0)
        await sessions._on_stream(failed, {"kind": "error", "reason": "received 1011 (internal error) Transcription provider stream error"})
        await asyncio.sleep(0.2)
        return failed

    failed = asyncio.run(scenario())
    fresh = sessions.active["rep"]
    assert fresh is not failed and failed.ended
    # From 3 s before the last settled words: 6.0 - 3.0 = 3.0 s, to the end of what was heard (10 s).
    assert fresh.offset_s == 3.0
    assert len(fresh.fed) == 7 * live.BYTES_PER_SECOND
    # The client drops the side's text from there and takes the replay's; it is not told of an error.
    assert {"type": "ChannelReset", "audio_channel": "rep", "from": 3.0, "language": sessions.sides["rep"].language} in client.sent
    assert not [m for m in client.sent if m.get("type") == "Error"]
    # The other side is untouched.
    assert sessions.active.get("prospect") is None or sessions.active["prospect"].offset_s == 0.0


def test_a_side_that_cannot_be_reopened_is_given_up_and_the_client_is_told(monkeypatch):
    import asyncio

    live, sessions, client = _sessions(monkeypatch)
    monkeypatch.setattr(live, "MAX_RECOVERIES", 3)

    async def scenario():
        failed = sessions._open("rep", "es", "bilingual-en", offset_s=0.0)
        sessions.active["rep"] = failed
        sessions.buffers["rep"].append(bytes(4 * live.BYTES_PER_SECOND))
        _FakeStream.starts = False  # every new stream fails to connect
        await sessions._on_stream(failed, {"kind": "error", "reason": "gateway down"})
        await asyncio.sleep(0.6)
        return failed

    failed = asyncio.run(scenario())
    assert sessions.active["rep"] is failed
    assert sessions.recoveries["rep"] == 3
    assert [m for m in client.sent if m.get("type") == "Error"] == [{"type": "Error", "provider": "mai", "error": "gateway down"}]
    # One stream to start with, then one new attempt each time.
    assert len(_FakeStream.made) == 1 + 3


def test_a_stream_that_settles_words_again_clears_its_sides_failures(monkeypatch):
    import asyncio

    live, sessions, _ = _sessions(monkeypatch)

    async def scenario():
        stream = sessions._open("rep", "es", "bilingual-en", offset_s=0.0)
        sessions.active["rep"] = stream
        sessions.recoveries["rep"] = 4
        await sessions._on_stream(stream, {"kind": "final", "transcript": "Hola.", "start": 0.0, "end": 1.0, "words": []})

    asyncio.run(scenario())
    assert sessions.recoveries["rep"] == 0


def test_a_stream_ending_normally_or_a_closing_session_is_not_reopened(monkeypatch):
    import asyncio

    live, sessions, client = _sessions(monkeypatch)

    async def scenario():
        failed = sessions._open("rep", "es", "bilingual-en", offset_s=0.0)
        sessions.active["rep"] = failed
        sessions.closing = True
        await sessions._on_stream(failed, {"kind": "error", "reason": "closed"})
        await asyncio.sleep(0.1)

    asyncio.run(scenario())
    assert len(_FakeStream.made) == 1
    assert [m for m in client.sent if m.get("type") == "Error"]


def test_a_mai_stream_reopened_mid_call_starts_its_sentences_at_its_offset():
    from app.services.live_channel_sessions import MaiStream

    stream = MaiStream("rep", "es", None, vocab=[], offset_s=0.0, on_event=_noop)
    stream.offset_s = 12.5  # given after it was built, as a restart does
    stream.feed(b"\0" * 32000)
    event = stream.events({"type": "transcript-delta", "delta": "Hola."})[0]
    assert (event["start"], event["end"]) == (12.5, 13.5)
