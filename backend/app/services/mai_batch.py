"""File speech to text with MAI-Transcribe-2 through OpenRouter (STT_PROVIDER=mai).

The endpoint answers a request at once, so a recording is decoded to 16 kHz mono first. Who spoke comes from the
recording itself:
  - two separate channels (a phone call recorded one side per channel): the mixed audio is transcribed with MAI's
    diarizing request, which cuts it into turns with times and clean text, and each turn is given to the channel
    that is louder while it lasts. A voice leaks faintly into the other channel, so transcribing the channels one by
    one made that leak into words; the energy only has to say which side a turn belongs to. S1 is the rep, S2 the
    other party; the rep is the channel the caller says it is (rep_channel), unless the words say otherwise (the
    other channel is the one introducing itself and pitching);
  - one channel: the same request, speakers numbered S1, S2 in order of first appearance. They only hold within a
    request, so a recording longer than DIARIZE_MAX_S raises and the router falls back to Deepgram;
  - diarization=False: plain text, the recording cut at pauses into chunks of at most MAX_CHUNK_S, one line each.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

import numpy as np

from app.config import settings
from app.services.live_chunker import BYTES_PER_SECOND, ChunkCutter
from app.services.openrouter_stt import MODEL, OpenRouterTranscriber
from app.services.transcript_sanitize import rep_voice_score

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
MAX_CHUNK_S = 30.0
PARALLEL = 6
HEDGE_S = 8.0
GIVE_UP_S = 60.0
# A request carries this much audio at most (~10 MB), and a longer recording is cut into windows of this length.
WINDOW_S = 300.0
DIARIZE_GIVE_UP_S = 240.0
# A single-channel recording is diarized in one request, since speaker numbers do not carry over between requests.
DIARIZE_MAX_S = 600.0
# Both channels carry the same audio (a mono recording saved as stereo) when they differ by less than this share.
SEPARATE_CHANNELS_RATIO = 0.2
# A turn belongs to a channel when that channel is this much louder (dB) than the other while the turn lasts.
CLEAR_DB = 3.0
# How far ahead the other channel must sound like the rep before the channel the caller named is overruled.
ROLE_SWAP_MARGIN = 4


@dataclass(frozen=True)
class MaiTranscript:
    text: str
    chunks: int
    cost_usd: Optional[float]
    speakers: str = "none"  # "channels" | "diarized" | "none"
    roles_known: bool = False  # the channel that is the rep was told by the caller, not guessed from the words


async def decode_pcm_16k_mono(audio: bytes, channel: Optional[int] = None) -> bytes:
    """The recording as 16 kHz mono PCM: all channels mixed, or only `channel` of them."""
    pick = [] if channel is None else ["-af", f"pan=mono|c0=c{channel}"]
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", *pick,
        "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "pipe:1",
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


def _samples(pcm: bytes) -> np.ndarray:
    return np.frombuffer(pcm, dtype=np.int16, count=len(pcm) // 2)


def are_separate_channels(left: bytes, right: bytes) -> bool:
    """False when the two channels are the same audio, so there is nothing to tell the sides apart by."""
    n = min(len(left), len(right)) // 2
    if n == 0:
        return False
    a = _samples(left)[:n].astype(np.int32)
    b = _samples(right)[:n].astype(np.int32)
    loudest = max(np.abs(a).mean(), np.abs(b).mean())
    return bool(loudest > 0 and np.abs(a - b).mean() / loudest > SEPARATE_CHANNELS_RATIO)


def window_bounds(pcm: bytes, window_s: float = WINDOW_S, reach_s: float = 5.0) -> list[tuple[int, int]]:
    """Sample ranges of at most about window_s each, every cut at the quietest tenth of a second near its mark."""
    x = np.abs(_samples(pcm).astype(np.int32))
    total, step, hop = len(x), int(window_s * SAMPLE_RATE), SAMPLE_RATE // 10
    cuts = [0]
    while total - cuts[-1] > step * 1.2:
        mark = cuts[-1] + step
        lo, hi = max(cuts[-1] + hop, mark - int(reach_s * SAMPLE_RATE)), min(total - hop, mark + int(reach_s * SAMPLE_RATE))
        frames = [x[i:i + hop].mean() for i in range(lo, hi, hop)]
        cuts.append(lo + int(np.argmin(frames)) * hop if frames else mark)
    cuts.append(total)
    return list(zip(cuts[:-1], cuts[1:]))


def _db_over(left: np.ndarray, right: np.ndarray, start: float, end: float) -> float:
    """How much louder (dB) the left channel is than the right between two moments; positive means left."""
    a, b = int(start * SAMPLE_RATE), max(int(end * SAMPLE_RATE), int(start * SAMPLE_RATE) + 1)
    rms = lambda x: float(np.sqrt(np.mean(x[a:b].astype(np.float64) ** 2))) if len(x[a:b]) else 0.0
    return 20 * float(np.log10((rms(left) + 1.0) / (rms(right) + 1.0)))


def assign_channels(turns: list[dict], left: np.ndarray, right: np.ndarray, offset_s: float) -> list[int]:
    """Channel (0 or 1) of every turn of one request: the louder one while it lasts. A turn too close to call goes to
    the channel its own speaker number mostly landed on in this request, then to whichever is louder."""
    diffs = [_db_over(left, right, offset_s + t["start"], offset_s + t["end"]) for t in turns]
    votes: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for t, d in zip(turns, diffs):
        if abs(d) >= CLEAR_DB:
            votes[t["speaker"]][0 if d > 0 else 1] += t["end"] - t["start"] + 0.1
    out = []
    for t, d in zip(turns, diffs):
        if abs(d) < CLEAR_DB and votes[t["speaker"]][0] != votes[t["speaker"]][1]:
            out.append(0 if votes[t["speaker"]][0] > votes[t["speaker"]][1] else 1)
        else:
            out.append(0 if d >= 0 else 1)
    return out


def pick_rep_channel(sides: list[list[str]], rep_channel: Optional[int]) -> int:
    scores = [sum(rep_voice_score(text) for text in side) for side in sides]
    named = rep_channel if rep_channel in (0, 1) else (1 if scores[1] > scores[0] else 0)
    other = 1 - named
    return other if scores[other] - scores[named] >= ROLE_SWAP_MARGIN else named


def join_turns(turns: list[tuple[int, str]]) -> str:
    """S<n>: text lines; neighbours from the same speaker become one."""
    merged: list[list] = []
    for speaker, text in turns:
        if merged and merged[-1][0] == speaker:
            merged[-1][1] += " " + text
        else:
            merged.append([speaker, text])
    return "\n".join(f"S{speaker}: {text}" for speaker, text in merged)


def number_by_appearance(turns: list[dict]) -> list[tuple[int, str]]:
    order: dict[int, int] = {}
    return [(order.setdefault(t["speaker"], len(order) + 1), t["text"]) for t in turns]


def _total(costs: list[Optional[float]]) -> Optional[float]:
    known = [c for c in costs if c is not None]
    return sum(known) if known else None


async def transcribe_mai(
    audio: bytes,
    *,
    language: Optional[str],
    channels: int = 1,
    rep_channel: Optional[int] = None,
    diarization: bool = True,
) -> MaiTranscript:
    api_key = getattr(settings, "OPENROUTER_API_KEY", None)
    if not api_key or not str(api_key).strip():
        raise RuntimeError("MAI STT needs OPENROUTER_API_KEY")

    mixed = await decode_pcm_16k_mono(audio)
    seconds = len(mixed) / BYTES_PER_SECOND
    sides: Optional[tuple[np.ndarray, np.ndarray]] = None
    if diarization and channels >= 2:
        left, right = await asyncio.gather(decode_pcm_16k_mono(audio, 0), decode_pcm_16k_mono(audio, 1))
        if are_separate_channels(left, right):
            sides = (_samples(left), _samples(right))
        else:
            logger.info("MAI STT: the two channels carry the same audio; treating the recording as mono")
    if diarization and sides is None and seconds > DIARIZE_MAX_S:
        raise RuntimeError(f"recording is longer than {DIARIZE_MAX_S:.0f}s, too long to diarize in one request")

    chunks = cut_chunks(mixed)
    if not chunks:
        return MaiTranscript(text="", chunks=0, cost_usd=None)

    transcriber = OpenRouterTranscriber(
        api_key, language=language, hedge_s=HEDGE_S, give_up_s=DIARIZE_GIVE_UP_S if diarization else GIVE_UP_S
    )
    gate = asyncio.Semaphore(PARALLEL)

    async def guarded(call):
        async with gate:
            return await call

    try:
        if not diarization:
            results = await asyncio.gather(*(guarded(transcriber.transcribe(c.pcm)) for c in chunks))
            return MaiTranscript(
                text="\n".join(r.text for r in results if r.text),
                chunks=len(chunks),
                cost_usd=_total([r.cost_usd for r in results]),
            )

        bounds = window_bounds(mixed) if sides else [(0, len(mixed) // 2)]
        windows = await asyncio.gather(
            *(guarded(transcriber.diarize(mixed[a * 2:b * 2])) for a, b in bounds)
        )
        cost = _total([c for _, c in windows])
        if not sides:
            return MaiTranscript(
                text=join_turns(number_by_appearance(windows[0][0])), chunks=1, cost_usd=cost, speakers="diarized"
            )

        placed: list[tuple[int, str]] = []  # (channel, text) in time order
        for (a, _), (turns, _) in zip(bounds, windows):
            for channel, turn in zip(assign_channels(turns, sides[0], sides[1], a / SAMPLE_RATE), turns):
                placed.append((channel, turn["text"]))
        rep = pick_rep_channel(
            [[text for channel, text in placed if channel == c] for c in (0, 1)], rep_channel
        )
        return MaiTranscript(
            text=join_turns([(1 if channel == rep else 2, text) for channel, text in placed]),
            chunks=len(bounds),
            cost_usd=cost,
            speakers="channels",
            roles_known=rep_channel in (0, 1),
        )
    finally:
        await transcriber.aclose()


__all__ = ["MODEL", "MaiTranscript", "transcribe_mai"]
