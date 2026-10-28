"""Speech to text through OpenRouter's transcription endpoint, one request per chunk of speech.

The endpoint answers a whole chunk at once (no partial text), so a live call is cut into chunks (live_chunker) and each one
is sent as it closes. Requests sometimes stall (one took 25 s in a 5 minute test; about a third of a run's slowest ones were
over a second): a chunk's request is sent a second time when the first has not answered after HEDGE_S, and whichever
answers first is used. The second request only costs money when the first was slow.
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import time
import wave
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

URL = "https://openrouter.ai/api/v1/audio/transcriptions"
MODEL = "microsoft/mai-transcribe-2"
HEDGE_S = 1.0
# A chunk whose requests have not answered by now is given up (the call goes on; its words are lost).
GIVE_UP_S = 20.0
SAMPLE_RATE = 16000


class TranscriptionError(RuntimeError):
    pass


@dataclass
class Transcription:
    text: str
    requests: int  # how many were sent for this chunk (2 when the hedge went out)
    hedged: bool
    winner: str  # "first" | "hedge"
    latency_s: float  # until the answer that was used
    cost_usd: Optional[float]  # what the winning response reported, when it did


def wav_bytes(pcm: bytes, rate: int = SAMPLE_RATE) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


class OpenRouterTranscriber:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = MODEL,
        language: Optional[str] = None,
        hedge_s: float = HEDGE_S,
        give_up_s: float = GIVE_UP_S,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.language = language
        self.hedge_s = hedge_s
        self.give_up_s = give_up_s
        # One client per call: the connection stays open between chunks (a first request on a cold connection took 1.8-2.8 s).
        self.client = client or httpx.AsyncClient(timeout=httpx.Timeout(give_up_s, connect=5.0))
        self.owns_client = client is None

    async def aclose(self) -> None:
        if self.owns_client:
            await self.client.aclose()

    async def warm_up(self) -> None:
        """A tiny request of silence when the call starts, so the first chunk finds an open connection."""
        try:
            await self._once(wav_bytes(bytes(SAMPLE_RATE // 3 * 2)))
        except Exception as e:  # never at the cost of the call
            logger.info("OpenRouter STT warm-up failed: %s", e)

    async def _once(self, wav: bytes) -> tuple[str, Optional[float]]:
        body: dict = {
            "model": self.model,
            "input_audio": {"data": base64.b64encode(wav).decode(), "format": "wav"},
            "temperature": 0,
        }
        if self.language:
            body["language"] = self.language
        response = await self.client.post(URL, headers={"Authorization": f"Bearer {self.api_key}"}, json=body)
        if response.status_code != 200:
            raise TranscriptionError(f"OpenRouter {response.status_code}: {response.text[:200]}")
        data = response.json()
        cost = (data.get("usage") or {}).get("cost")
        return str(data.get("text") or "").strip(), cost if isinstance(cost, (int, float)) else None

    async def diarize(self, pcm: bytes) -> tuple[list[dict], Optional[float]]:
        """One request for a stretch of audio: [{speaker, start, end, text}] in order, times in seconds from the start of
        the audio. The speaker numbers hold within this request only. Raises TranscriptionError when no speakers came back."""
        body: dict = {
            "model": self.model,
            "input_audio": {"data": base64.b64encode(wav_bytes(pcm)).decode(), "format": "wav"},
            "temperature": 0,
            "response_format": "verbose_json",
            "diarize": True,
        }
        if self.language:
            body["language"] = self.language
        response = await self.client.post(URL, headers={"Authorization": f"Bearer {self.api_key}"}, json=body)
        if response.status_code != 200:
            raise TranscriptionError(f"OpenRouter {response.status_code}: {response.text[:200]}")
        data = response.json()
        turns = [
            {"speaker": s["speaker"], "start": float(s["start"]), "end": float(s["end"]), "text": str(s.get("text") or "").strip()}
            for s in data.get("segments") or []
            if isinstance(s.get("speaker"), int) and isinstance(s.get("start"), (int, float))
            and isinstance(s.get("end"), (int, float)) and str(s.get("text") or "").strip()
        ]
        if not turns:
            raise TranscriptionError("the response carried no speaker labels")
        cost = (data.get("usage") or {}).get("cost")
        return turns, cost if isinstance(cost, (int, float)) else None

    async def transcribe(self, pcm: bytes) -> Transcription:
        """The chunk's text. Raises TranscriptionError when no request answered."""
        wav = wav_bytes(pcm)
        started = time.monotonic()
        first = asyncio.create_task(self._once(wav))
        tasks = {first: "first"}
        hedged = False
        errors: list[str] = []
        try:
            while True:
                waiting = set(tasks)
                timeout = None
                if not hedged:
                    timeout = max(0.0, self.hedge_s - (time.monotonic() - started))
                remaining = self.give_up_s - (time.monotonic() - started)
                if remaining <= 0:
                    raise TranscriptionError("; ".join(errors) or f"no answer in {self.give_up_s:.0f}s")
                done, _ = await asyncio.wait(
                    waiting,
                    timeout=min(timeout, remaining) if timeout is not None else remaining,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in done:
                    who = tasks.pop(task)
                    try:
                        text, cost = task.result()
                    except Exception as e:
                        errors.append(f"{who}: {e}")
                        continue
                    return Transcription(
                        text=text,
                        requests=1 + int(hedged),
                        hedged=hedged,
                        winner=who,
                        latency_s=time.monotonic() - started,
                        cost_usd=cost,
                    )
                # Nothing answered: the hedge goes out when the first is slow, or when it failed.
                if not hedged and (not tasks or time.monotonic() - started >= self.hedge_s - 1e-6):
                    hedged = True
                    tasks[asyncio.create_task(self._once(wav))] = "hedge"
                elif not tasks:
                    raise TranscriptionError("; ".join(errors) or "no request answered")
        finally:
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
