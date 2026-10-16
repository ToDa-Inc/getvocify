import asyncio
import base64
import io
import json
import wave

import httpx
import pytest

from app.services.openrouter_stt import OpenRouterTranscriber, TranscriptionError, wav_bytes

PCM = bytes(16000 * 2)  # 1 s of silence


def transcriber(handler, **kwargs):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenRouterTranscriber("key", client=client, **kwargs)


def ok(text, cost=0.0000278):
    return httpx.Response(200, json={"text": text, "usage": {"seconds": 1, "cost": cost}})


def test_a_chunk_is_sent_as_a_wav_with_the_model_and_the_language():
    seen = []

    async def handler(request):
        seen.append(request)
        return ok(" Hola, buenas. ")

    result = asyncio.run(transcriber(handler, language="es").transcribe(PCM))
    assert result.text == "Hola, buenas." and result.requests == 1 and not result.hedged and result.winner == "first"
    assert result.cost_usd == pytest.approx(0.0000278)
    request = seen[0]
    assert request.headers["authorization"] == "Bearer key"
    body = json.loads(request.content)
    assert body["model"] == "microsoft/mai-transcribe-2" and body["language"] == "es" and body["temperature"] == 0
    assert body["input_audio"]["format"] == "wav"
    with wave.open(io.BytesIO(base64.b64decode(body["input_audio"]["data"]))) as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()) == (1, 2, 16000, 16000)


def test_without_a_language_the_transcriber_detects_it():
    seen = []

    async def handler(request):
        seen.append(json.loads(request.content))
        return ok("Bon dia")

    asyncio.run(transcriber(handler).transcribe(PCM))
    assert "language" not in seen[0]


def test_a_request_that_stalls_is_answered_by_its_second():
    calls = []

    async def handler(request):
        calls.append(1)
        if len(calls) == 1:
            await asyncio.sleep(5)  # the stalled one
        return ok("Mándame un mail")

    async def scenario():
        t = transcriber(handler, hedge_s=0.05)
        return await t.transcribe(PCM)

    result = asyncio.run(asyncio.wait_for(scenario(), 2.0))
    assert result.text == "Mándame un mail" and result.hedged and result.winner == "hedge" and result.requests == 2
    assert result.latency_s < 1.0


def test_a_fast_first_request_sends_no_second_one():
    calls = []

    async def handler(request):
        calls.append(1)
        await asyncio.sleep(0.02)
        return ok("Sí")

    async def scenario():
        result = await transcriber(handler, hedge_s=0.5).transcribe(PCM)
        await asyncio.sleep(0.6)  # the hedge would have gone out by now
        return result

    result = asyncio.run(scenario())
    assert result.requests == 1 and len(calls) == 1


def test_a_failed_request_is_retried_at_once_not_after_the_hedge_wait():
    calls = []

    async def handler(request):
        calls.append(1)
        return httpx.Response(502, text="bad gateway") if len(calls) == 1 else ok("Vale")

    async def scenario():
        return await transcriber(handler, hedge_s=5.0).transcribe(PCM)

    result = asyncio.run(asyncio.wait_for(scenario(), 2.0))
    assert result.text == "Vale" and result.winner == "hedge"


def test_a_chunk_nothing_answered_raises():
    async def handler(request):
        return httpx.Response(500, text="down")

    with pytest.raises(TranscriptionError):
        asyncio.run(transcriber(handler, hedge_s=0.01).transcribe(PCM))


def test_a_chunk_that_never_answers_is_given_up():
    async def handler(request):
        await asyncio.sleep(30)

    async def scenario():
        return await transcriber(handler, hedge_s=0.05, give_up_s=0.3).transcribe(PCM)

    with pytest.raises(TranscriptionError):
        asyncio.run(asyncio.wait_for(scenario(), 3.0))


def test_the_warm_up_never_raises():
    async def handler(request):
        return httpx.Response(500, text="down")

    asyncio.run(transcriber(handler).warm_up())


def test_wav_bytes_wraps_pcm16():
    with wave.open(io.BytesIO(wav_bytes(PCM))) as wav:
        assert wav.getframerate() == 16000 and wav.getnframes() == 16000
