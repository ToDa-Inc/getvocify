import httpx
import numpy as np
import pytest

from app.config import settings
from app.services import mai_batch, stt_batch
from app.services.openrouter_stt import OpenRouterTranscriber, Transcription, TranscriptionError

RATE = mai_batch.SAMPLE_RATE


def _pcm(*parts):
    """Audio of the given (seconds, level) stretches as 16-bit PCM."""
    return np.concatenate([np.full(int(s * RATE), lvl, dtype=np.int16) for s, lvl in parts])


def test_stt_provider_accepts_mai():
    assert settings.__class__(STT_PROVIDER=" MAI ").STT_PROVIDER == "mai"


def test_cut_chunks_never_exceeds_the_max_and_skips_silence():
    assert mai_batch.cut_chunks(bytes(16000 * 2 * 5)) == []


def test_channels_that_are_the_same_audio_are_not_two_sides():
    a = _pcm((1, 2000), (1, 300)).tobytes()
    assert not mai_batch.are_separate_channels(a, a)
    assert mai_batch.are_separate_channels(_pcm((1, 2000), (1, 0)).tobytes(), _pcm((1, 0), (1, 2000)).tobytes())
    assert not mai_batch.are_separate_channels(bytes(100), bytes(100))


def test_a_turn_goes_to_the_louder_channel_and_leaked_voices_do_not_count():
    # 0-2 s: the rep speaks (a faint leak reaches the right channel); 2-4 s: the contact speaks.
    left = _pcm((2, 3000), (2, 100))
    right = _pcm((2, 150), (2, 2500))
    turns = [
        {"speaker": 0, "start": 0.2, "end": 1.8, "text": "a"},
        {"speaker": 1, "start": 2.2, "end": 3.8, "text": "b"},
    ]
    assert mai_batch.assign_channels(turns, left, right, 0.0) == [0, 1]


def test_a_turn_too_close_to_call_follows_its_speaker_number():
    left = _pcm((2, 3000), (2, 100), (2, 1000))
    right = _pcm((2, 150), (2, 2500), (2, 1000))
    turns = [
        {"speaker": 7, "start": 0.2, "end": 1.8, "text": "clear left"},
        {"speaker": 3, "start": 2.2, "end": 3.8, "text": "clear right"},
        {"speaker": 3, "start": 4.2, "end": 5.8, "text": "equal energy"},
    ]
    assert mai_batch.assign_channels(turns, left, right, 0.0) == [0, 1, 1]


def test_turns_are_placed_inside_their_window():
    left = _pcm((10, 100), (2, 3000))
    right = _pcm((10, 100), (2, 150))
    turns = [{"speaker": 0, "start": 0.5, "end": 1.5, "text": "x"}]
    assert mai_batch.assign_channels(turns, left, right, 10.0) == [0]


def test_long_recordings_are_cut_at_a_quiet_moment():
    pcm = _pcm((302, 2000), (1, 0), (300, 2000)).tobytes()
    bounds = mai_batch.window_bounds(pcm, window_s=300)
    assert len(bounds) == 2 and bounds[0][1] == bounds[1][0]
    assert abs(bounds[0][1] / RATE - 302.5) < 1.0
    assert mai_batch.window_bounds(_pcm((100, 2000)).tobytes(), window_s=300) == [(0, 100 * RATE)]


def test_the_named_channel_is_the_rep_unless_the_other_one_clearly_introduces_itself():
    pitch = ["Hola, Jaume, soy Dani, fundador de Vocify. Te llamo porque he visto que llevas el equipo de ventas."]
    reply = ["Dígame.", "Sí, dígame."]
    assert mai_batch.pick_rep_channel([reply, pitch], rep_channel=0) == 1
    assert mai_batch.pick_rep_channel([pitch, reply], rep_channel=0) == 0
    assert mai_batch.pick_rep_channel([["Vale.", "Sí."], ["Ya.", "Mm."]], rep_channel=1) == 1
    assert mai_batch.pick_rep_channel([reply, pitch], rep_channel=None) == 1
    assert mai_batch.pick_rep_channel([["Vale."], ["Sí."]], rep_channel=None) == 0


def test_neighbours_from_the_same_speaker_become_one_line():
    assert mai_batch.join_turns([(1, "a"), (1, "b"), (2, "c"), (1, "d")]) == "S1: a b\nS2: c\nS1: d"
    turns = [{"speaker": 5, "text": "a"}, {"speaker": 2, "text": "b"}, {"speaker": 5, "text": "c"}]
    assert mai_batch.number_by_appearance(turns) == [(1, "a"), (2, "b"), (1, "c")]


class _FakeTranscriber:
    plain_texts = ["uno", "dos"]
    segments = []
    calls = []

    def __init__(self, *a, **k):
        pass

    async def transcribe(self, pcm):
        return Transcription(
            text=self.plain_texts.pop(0), requests=1, hedged=False, winner="first", latency_s=0.1, cost_usd=0.01
        )

    async def diarize(self, pcm):
        type(self).calls.append(len(pcm))
        return list(self.segments), 0.02

    async def aclose(self):
        pass


@pytest.fixture
def fake(monkeypatch):
    _FakeTranscriber.plain_texts = ["uno", "dos"]
    _FakeTranscriber.segments = []
    _FakeTranscriber.calls = []
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(mai_batch, "OpenRouterTranscriber", _FakeTranscriber)
    # Two voices alternate in 8 s of audio: the rep (channel 0) first, the contact (channel 1) second.
    left, right = _pcm((4, 3000), (4, 100)), _pcm((4, 150), (4, 2500))
    both = (left.astype(np.int32) + right).clip(-32768, 32767).astype(np.int16)

    async def decode(audio, channel=None):
        return {None: both, 0: left, 1: right}[channel].tobytes()

    monkeypatch.setattr(mai_batch, "decode_pcm_16k_mono", decode)
    monkeypatch.setattr(mai_batch, "cut_chunks", lambda pcm: [type("C", (), {"pcm": b"x"})(), type("C", (), {"pcm": b"y"})()])
    return _FakeTranscriber


async def test_plain_text_is_one_line_per_chunk_in_order(fake):
    out = await mai_batch.transcribe_mai(b"a", language="es", diarization=False)
    assert out.text == "uno\ndos" and out.chunks == 2 and out.cost_usd == pytest.approx(0.02) and out.speakers == "none"


async def test_two_channels_label_the_rep_s1_and_the_contact_s2(fake):
    fake.segments = [
        {"speaker": 0, "start": 0.2, "end": 3.8, "text": "Hola, Jaume."},
        {"speaker": 1, "start": 4.2, "end": 7.8, "text": "Dígame."},
    ]
    out = await mai_batch.transcribe_mai(b"a", language="es", channels=2, rep_channel=0)
    assert out.text == "S1: Hola, Jaume.\nS2: Dígame."
    assert (out.speakers, out.roles_known, out.cost_usd) == ("channels", True, 0.02)


async def test_the_model_speaker_numbers_do_not_decide_the_sides_on_two_channels(fake):
    fake.segments = [
        {"speaker": 1, "start": 0.2, "end": 3.8, "text": "Hola, Jaume."},
        {"speaker": 0, "start": 4.2, "end": 7.8, "text": "Dígame."},
    ]
    out = await mai_batch.transcribe_mai(b"a", language="es", channels=2, rep_channel=0)
    assert out.text == "S1: Hola, Jaume.\nS2: Dígame."


async def test_the_words_overrule_the_named_channel_when_they_are_clear(fake):
    fake.segments = [
        {"speaker": 0, "start": 0.2, "end": 3.8, "text": "Dígame."},
        {"speaker": 1, "start": 4.2, "end": 7.8, "text": "Hola, Jaume, soy Dani, fundador de Vocify. Te llamo porque he visto que llevas el equipo."},
    ]
    out = await mai_batch.transcribe_mai(b"a", language="es", channels=2, rep_channel=0)
    assert out.text.splitlines()[0] == "S2: Dígame."
    assert out.text.splitlines()[1].startswith("S1: Hola, Jaume, soy Dani")


async def test_an_unknown_rep_channel_is_decided_by_the_words_and_not_trusted(fake):
    fake.segments = [{"speaker": 0, "start": 0.2, "end": 3.8, "text": "Dígame."}]
    out = await mai_batch.transcribe_mai(b"a", language="es", channels=2, rep_channel=None)
    assert out.roles_known is False and out.speakers == "channels"


async def test_one_channel_is_diarized_in_one_request_and_numbered_by_appearance(fake):
    fake.segments = [
        {"speaker": 4, "start": 0.2, "end": 3.8, "text": "Hola."},
        {"speaker": 9, "start": 4.2, "end": 7.8, "text": "Sí."},
        {"speaker": 4, "start": 8.0, "end": 8.5, "text": "Vale."},
    ]
    out = await mai_batch.transcribe_mai(b"a", language="es", channels=1)
    assert out.text == "S1: Hola.\nS2: Sí.\nS1: Vale."
    assert (out.speakers, out.roles_known, len(fake.calls)) == ("diarized", False, 1)


async def test_two_channels_with_the_same_audio_are_diarized_as_one(fake, monkeypatch):
    mono = _pcm((8, 2000)).tobytes()

    async def decode(audio, channel=None):
        return mono

    monkeypatch.setattr(mai_batch, "decode_pcm_16k_mono", decode)
    fake.segments = [{"speaker": 0, "start": 0.2, "end": 3.8, "text": "Hola."}]
    out = await mai_batch.transcribe_mai(b"a", language="es", channels=2, rep_channel=0)
    assert (out.speakers, out.roles_known) == ("diarized", False)


async def test_a_mono_recording_too_long_for_one_request_raises(fake, monkeypatch):
    long = _pcm((int(mai_batch.DIARIZE_MAX_S) + 5, 2000)).tobytes()

    async def decode(audio, channel=None):
        return long

    monkeypatch.setattr(mai_batch, "decode_pcm_16k_mono", decode)
    with pytest.raises(RuntimeError, match="too long"):
        await mai_batch.transcribe_mai(b"a", language="es", channels=1)


async def test_silence_is_an_empty_transcript_without_a_request(fake, monkeypatch):
    monkeypatch.setattr(mai_batch, "cut_chunks", lambda pcm: [])
    out = await mai_batch.transcribe_mai(b"a", language="es", channels=2)
    assert out.text == "" and fake.calls == []


async def test_the_router_reports_the_sides_and_who_made_them(monkeypatch):
    async def mai(*a, **k):
        assert k["channels"] == 2 and k["rep_channel"] == 0
        return mai_batch.MaiTranscript(text="S1: hola", chunks=1, cost_usd=None, speakers="channels", roles_known=True)

    monkeypatch.setattr(mai_batch, "transcribe_mai", mai)
    r = await stt_batch._transcribe_once(
        b"a", content_type="audio/wav", provider="mai", lang="es", sm_lang="es", sm_lang_id=None,
        user_id=None, extra_terms=None, diarization=True, t0=0.0, multichannel=True, rep_channel=0,
    )
    assert (r.diarization, r.channels, r.provider, r.roles_known) == ("channel", 2, "openrouter", True)
    assert r.model == mai_batch.MODEL


async def test_router_falls_back_to_deepgram_when_mai_fails(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("down")

    monkeypatch.setattr(mai_batch, "transcribe_mai", boom)

    class DG:
        async def transcribe(self, **k):
            return "hola", 0.9

    import app.services.deepgram_batch as dg
    monkeypatch.setattr(dg, "DeepgramBatchService", DG)
    r = await stt_batch._transcribe_once(
        b"a", content_type="audio/mpeg", provider="mai", lang="es", sm_lang="es", sm_lang_id=None,
        user_id=None, extra_terms=None, diarization=True, t0=0.0,
    )
    assert r.text == "hola" and r.provider == "deepgram" and not r.roles_known


def _client(payload, status=200):
    seen = []

    def handler(request):
        seen.append(request.read())
        return httpx.Response(status, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), seen


async def test_diarize_asks_for_speakers_and_returns_timed_turns():
    client, seen = _client({
        "segments": [
            {"id": 0, "start": 1.5, "end": 1.9, "text": "Dígame.", "speaker": 0},
            {"id": 1, "start": 3, "end": 3.7, "text": " ", "speaker": 1},
            {"id": 2, "start": 4, "end": 5, "text": "Hola.", "speaker": 1},
        ],
        "usage": {"cost": 0.002},
    })
    turns, cost = await OpenRouterTranscriber("k", language="es", client=client).diarize(b"\0\0" * 100)
    assert turns == [
        {"speaker": 0, "start": 1.5, "end": 1.9, "text": "Dígame."},
        {"speaker": 1, "start": 4.0, "end": 5.0, "text": "Hola."},
    ]
    assert cost == 0.002
    assert b'"diarize":true' in seen[0].replace(b" ", b"") and b"verbose_json" in seen[0]


async def test_diarize_without_speaker_labels_is_an_error_not_an_unlabelled_transcript():
    client, _ = _client({"text": "hola", "segments": [{"id": 0, "start": 0, "end": 1, "text": "hola"}]})
    with pytest.raises(TranscriptionError, match="speaker"):
        await OpenRouterTranscriber("k", client=client).diarize(b"\0\0" * 100)
    client, _ = _client({"error": "x"}, status=500)
    with pytest.raises(TranscriptionError, match="500"):
        await OpenRouterTranscriber("k", client=client).diarize(b"\0\0" * 100)
