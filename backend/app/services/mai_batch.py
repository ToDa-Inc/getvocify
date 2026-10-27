"""File speech to text with MAI-Transcribe-2 through OpenRouter (STT_PROVIDER=mai).

The endpoint answers a whole chunk at once, so a recording is decoded to 16 kHz mono, cut at pauses
(live_chunker) into chunks of at most MAX_CHUNK_S, and the chunks are sent a few at a time. The text comes
back in order, one line per chunk. MAI does not tell speakers apart: the transcript has no speaker labels.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from app.config import settings
from app.services.live_chunker import ChunkCutter
from app.services.openrouter_stt import MODEL, OpenRouterTranscriber

logger = logging.getLogger(__name__)

MAX_CHUNK_S = 30.0
PARALLEL = 6
HEDGE_S = 8.0
GIVE_UP_S = 60.0


@dataclass(frozen=True)
class MaiTranscript:
    text: str
    chunks: int
    cost_usd: Optional[float]


async def decode_pcm_16k_mono(audio: bytes) -> bytes:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
        "-ac", "1", "-ar", "16000", "-f", "s16le", "pipe:1",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate(audio)
    if proc.returncode != 0 or not out:
        raise RuntimeError(f"ffmpeg could not decode the recording: {err.decode(errors='replace')[:300]}")
    return out


def cut_chunks(pcm: bytes) -> list:
    cutter = ChunkCutter(max_s=MAX_CHUNK_S)
    chunks, _ = cutter.feed(pcm)
    last, _ = cutter.flush("end")
    return [*chunks, *([last] if last else [])]


async def transcribe_mai(audio: bytes, *, language: Optional[str]) -> MaiTranscript:
    api_key = getattr(settings, "OPENROUTER_API_KEY", None)
    if not api_key or not str(api_key).strip():
        raise RuntimeError("MAI STT needs OPENROUTER_API_KEY")
    chunks = cut_chunks(await decode_pcm_16k_mono(audio))
    if not chunks:
        return MaiTranscript(text="", chunks=0, cost_usd=None)

    transcriber = OpenRouterTranscriber(api_key, language=language, hedge_s=HEDGE_S, give_up_s=GIVE_UP_S)
    gate = asyncio.Semaphore(PARALLEL)

    async def one(chunk):
        async with gate:
            return await transcriber.transcribe(chunk.pcm)

    try:
        results = await asyncio.gather(*(one(c) for c in chunks))
    finally:
        await transcriber.aclose()
    costs = [r.cost_usd for r in results if r.cost_usd is not None]
    return MaiTranscript(
        text="\n".join(r.text for r in results if r.text),
        chunks=len(chunks),
        cost_usd=sum(costs) if costs else None,
    )


__all__ = ["MODEL", "MaiTranscript", "transcribe_mai"]
