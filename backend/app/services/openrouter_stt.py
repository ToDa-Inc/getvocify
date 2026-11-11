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
from typing import Awaitable, Callable, Optional

import httpx

logger = logging.getLogger(__name__)

URL = "https://openrouter.ai/api/v1/audio/transcriptions"
MODEL = "microsoft/mai-transcribe-2"
HEDGE_S = 1.0
# A chunk whose requests have not answered by now is given up (the call goes on; its words are lost).
GIVE_UP_S = 20.0
# The provider answers 429 with «Retry-After: 1» or 2 when it has too many requests: the same request is sent again after
# that wait, this many times, instead of losing the speech. On 2026-11-11 it refused about half the requests for minutes;
# the first and its hedge were both refused within half a second and 45 pieces of live calls were lost in five minutes
# (a prospect asked «¿qué hacéis exactamente?» three times before any text arrived).
RATE_LIMIT_TRIES = 3
RATE_LIMIT_WAIT_S = 3.0
# The refusals come in a fixed cycle (about 4 s answering everything, then 6 s refusing everything, the wait asked for
# counting down to the reopening), and a second request in a closed stretch is refused too (same answer for two requests at
# the same instant in 35 of 36 seconds). So a chunk told to wait this long or more also goes to the backup (the streaming
# route, about 1.7 s for a piece), the hedge is not sent into a closed stretch, and the first answer of the two is used.
# A shorter wait is as fast as the backup.
BACKUP_MIN_WAIT_S = 2.0
SAMPLE_RATE = 16000


class TranscriptionError(RuntimeError):
    pass


@dataclass
class Transcription:
    text: str
    requests: int  # how many were sent for this chunk (2 when the hedge went out)
    hedged: bool
    winner: str  # "first" | "hedge" | "backup"
    latency_s: float  # until the answer that was used
    cost_usd: Optional[float]  # what the winning response reported, when it did
    backup: bool = False  # refused here and answered by the backup route


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
        phrases: Optional[list[str]] = None,
        hedge_s: float = HEDGE_S,
        give_up_s: float = GIVE_UP_S,
        client: Optional[httpx.AsyncClient] = None,
        backup: Optional[Callable[[bytes], Awaitable[str]]] = None,
    ) -> None:
        self.api_key = api_key
        # Another route for a chunk this one refuses: takes the chunk's PCM, returns its text.
        self.backup = backup
        self.model = model
        self.language = language
        # Words the transcriber should recognise as written (the company's glossary), passed to the provider behind MAI
        # (Azure's phrase list). «Vocify» came back as «Bossify», «Bowsify» and «Busify» without it and right with it, at
        # the same speed (0.38 s against 0.39 s). It also changes other pieces a little (about one in four of 59: capitals,
        # «okey» → «ok», a mumbled piece dropped), so it is sent only where asked for.
        self.phrases = [p for p in (phrases or []) if p and p.strip()]
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

    async def _once(self, wav: bytes, refused: Optional[Callable[[float], None]] = None) -> tuple[str, Optional[float]]:
        body: dict = {
            "model": self.model,
            "input_audio": {"data": base64.b64encode(wav).decode(), "format": "wav"},
            "temperature": 0,
        }
        if self.language:
            body["language"] = self.language
        phrases = self.phrases
        if phrases:
            body["provider"] = {"options": {"azure": {"phraseList": {"phrases": phrases}}}}
        response = await self._post(body, refused)
        if response.status_code == 400 and phrases:
            # The provider refused the list: the call goes on without it rather than without a transcript.
            logger.warning("OpenRouter STT: the phrase list was refused (%s); this call goes on without it", response.text[:200])
            self.phrases = []
            del body["provider"]
            response = await self._post(body, refused)
        if response.status_code != 200:
            raise TranscriptionError(f"OpenRouter {response.status_code}: {response.text[:200]}")
        data = response.json()
        cost = (data.get("usage") or {}).get("cost")
        return str(data.get("text") or "").strip(), cost if isinstance(cost, (int, float)) else None

    async def _post(self, body: dict, refused: Optional[Callable[[float], None]] = None) -> httpx.Response:
        """The request, sent again after the wait the provider asks for while it answers 429. `refused` is told that wait."""
        for attempt in range(RATE_LIMIT_TRIES + 1):
            response = await self.client.post(URL, headers={"Authorization": f"Bearer {self.api_key}"}, json=body)
            if response.status_code != 429 or attempt == RATE_LIMIT_TRIES:
                break
            try:
                wait = float(response.headers.get("retry-after") or 1.0)
            except ValueError:
                wait = 1.0
            if refused:
                refused(wait)
            await asyncio.sleep(min(RATE_LIMIT_WAIT_S, max(0.2, wait)))
        return response

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
        tasks: dict[asyncio.Task, str] = {}
        hedged = False
        backed = False
        closed_until = 0.0  # the provider said it answers nothing before then
        errors: list[str] = []
        wake = asyncio.Event()

        def refused(wait: float) -> None:
            nonlocal backed, closed_until
            closed_until = max(closed_until, time.monotonic() + wait)
            if self.backup is not None and not backed and wait >= BACKUP_MIN_WAIT_S:
                backed = True
                tasks[asyncio.create_task(self._backup(pcm))] = "backup"
            wake.set()

        tasks[asyncio.create_task(self._once(wav, refused))] = "first"
        waker = asyncio.create_task(wake.wait())
        try:
            while True:
                now = time.monotonic()
                remaining = self.give_up_s - (now - started)
                if remaining <= 0:
                    raise TranscriptionError("; ".join(errors) or f"no answer in {self.give_up_s:.0f}s")
                timeout = remaining
                if not hedged:
                    # The hedge goes out when the first is slow or has failed, never into a stretch the provider has closed.
                    waiting_on_a_request = any(who != "backup" for who in tasks.values())
                    due = max(started + self.hedge_s, closed_until) if waiting_on_a_request else closed_until
                    timeout = min(remaining, max(0.0, due - now))
                done, _ = await asyncio.wait({*tasks, waker}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
                if waker in done:
                    wake.clear()
                    waker = asyncio.create_task(wake.wait())
                for task in done:
                    who = tasks.pop(task, None)
                    if who is None:
                        continue
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
                        backup=who == "backup",
                    )
                # Nothing answered: the hedge goes out when the first is slow, or when it failed.
                now = time.monotonic()
                requests_left = any(who != "backup" for who in tasks.values())
                if not hedged and now >= closed_until and (not requests_left or now - started >= self.hedge_s - 1e-6):
                    hedged = True
                    tasks[asyncio.create_task(self._once(wav, refused))] = "hedge"
                elif not tasks and hedged:
                    raise TranscriptionError("; ".join(errors) or "no request answered")
        finally:
            waker.cancel()
            for task in tasks:
                task.cancel()
            await asyncio.gather(waker, *tasks, return_exceptions=True)

    async def _backup(self, pcm: bytes) -> tuple[str, Optional[float]]:
        return (await self.backup(pcm)).strip(), None  # type: ignore[misc]
