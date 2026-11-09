"""STT_PROVIDER=mai is MAI-2 only: a failure is tried again on MAI, never sent to Deepgram."""

import pytest

from app.services import stt_batch
from app.services.mai_batch import MaiTranscript


@pytest.fixture
def no_wait(monkeypatch):
    waits = []

    async def sleep(seconds):
        waits.append(seconds)

    monkeypatch.setattr(stt_batch.asyncio, "sleep", sleep)
    return waits


def _deepgram_must_not_run(monkeypatch):
    import app.services.deepgram_batch as deepgram

    class Never:
        def __init__(self, *a, **k):
            raise AssertionError("Deepgram must never transcribe when STT_PROVIDER=mai")

    monkeypatch.setattr(deepgram, "DeepgramBatchService", Never)


@pytest.mark.asyncio
async def test_a_429_is_retried_on_mai_and_the_transcript_is_mai(monkeypatch, no_wait):
    _deepgram_must_not_run(monkeypatch)
    calls = []

    async def transcribe_mai(audio, **kwargs):
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError('OpenRouter 429: {"error":{"message":"Provider returned 429"}}')
        return MaiTranscript(text="SPEAKER: S1\nHola", chunks=1, cost_usd=0.001, speakers="channels", roles_known=True)

    monkeypatch.setattr("app.services.mai_batch.transcribe_mai", transcribe_mai)
    result = await stt_batch._transcribe_mai_only(b"x", lang="es", multichannel=True, rep_channel=0, diarization=True, t0=0.0)
    assert result.text == "SPEAKER: S1\nHola" and result.provider == "openrouter"
    assert len(calls) == 3 and no_wait == [2.0, 5.0]


@pytest.mark.asyncio
async def test_when_mai_keeps_failing_the_error_is_raised_not_handed_to_deepgram(monkeypatch, no_wait):
    _deepgram_must_not_run(monkeypatch)

    async def transcribe_mai(audio, **kwargs):
        raise RuntimeError("OpenRouter 429")

    monkeypatch.setattr("app.services.mai_batch.transcribe_mai", transcribe_mai)
    with pytest.raises(RuntimeError, match="429"):
        await stt_batch._transcribe_mai_only(b"x", lang="es", multichannel=False, rep_channel=None, diarization=True, t0=0.0)
    assert no_wait == list(stt_batch.MAI_RETRY_WAITS_S)
