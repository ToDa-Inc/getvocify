import pytest

from app.config import settings
from app.services import mai_batch, stt_batch
from app.services.openrouter_stt import Transcription


def test_stt_provider_accepts_mai():
    assert settings.__class__(STT_PROVIDER=" MAI ").STT_PROVIDER == "mai"


def test_cut_chunks_never_exceeds_the_max_and_skips_silence():
    assert mai_batch.cut_chunks(bytes(16000 * 2 * 5)) == []


@pytest.mark.asyncio
async def test_mai_transcribes_chunks_in_order(monkeypatch):
    class Chunk:
        def __init__(self, pcm):
            self.pcm = pcm

    class Fake:
        def __init__(self, *a, **k): pass
        async def transcribe(self, pcm):
            return Transcription(text=pcm.decode(), requests=1, hedged=False, winner="first", latency_s=0.1, cost_usd=0.01)
        async def aclose(self): pass

    async def decode(audio): return b"x"
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(mai_batch, "OpenRouterTranscriber", Fake)
    monkeypatch.setattr(mai_batch, "decode_pcm_16k_mono", decode)
    monkeypatch.setattr(mai_batch, "cut_chunks", lambda pcm: [Chunk(b"uno"), Chunk(b"dos")])
    out = await mai_batch.transcribe_mai(b"a", language="es")
    assert out.text == "uno\ndos" and out.chunks == 2 and out.cost_usd == pytest.approx(0.02)


@pytest.mark.asyncio
async def test_router_falls_back_to_deepgram_when_mai_fails(monkeypatch):
    async def boom(*a, **k): raise RuntimeError("down")
    monkeypatch.setattr(mai_batch, "transcribe_mai", boom)

    class DG:
        async def transcribe(self, **k): return "hola", 0.9
    import app.services.deepgram_batch as dg
    monkeypatch.setattr(dg, "DeepgramBatchService", DG)
    r = await stt_batch._transcribe_once(
        b"a", content_type="audio/mpeg", provider="mai", lang="es", sm_lang="es", sm_lang_id=None,
        user_id=None, extra_terms=None, diarization=True, t0=0.0,
    )
    assert r.text == "hola"
