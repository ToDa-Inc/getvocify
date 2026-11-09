"""A desktop call's own recording, kept by the server while it transcribes the call live.

Live transcription hears a call in pieces of a few seconds, to show text at once; on unclear audio a piece is
sometimes heard in the wrong language (36 of 238 desktop calls, Oct-Nov 2026, against none of the calls transcribed
whole). So the server keeps both sides as they reach it, already on one clock (StreamClock), and when the session ends
it stores them as one stereo file: channel 0 the rep, channel 1 the other side. When the call is sent, its memo is
transcribed whole from that file (desktop_recording.py) and the note is written from that.

One file per live session: a call whose connection dropped and came back has several, named by when each began and
ended, so they are put back together in order.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import tempfile
import time
from typing import Any, Optional

from app.services.live_chunker import BYTES_PER_SECOND, SAMPLE_RATE

logger = logging.getLogger(__name__)

CAPTURE_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")
MIN_SECONDS = 3.0
# Rep first: the whole-call transcription reads channel 0 as the rep (rep_channel=0).
CHANNELS = ("rep", "prospect")


def part_name(capture_id: str, started_ms: int, ended_ms: int, ext: str) -> str:
    return f"live-{capture_id}-{started_ms}-{ended_ms}.{ext}"


class CallRecorder:
    """Both sides of one live session, written to disk as they arrive (never held in memory)."""

    def __init__(self, user_id: str, capture_id: str) -> None:
        self.user_id = user_id
        self.capture_id = capture_id
        self.started_ms = int(time.time() * 1000)
        self.dir = tempfile.mkdtemp(prefix="vocify-call-")
        self.paths = {label: os.path.join(self.dir, f"{label}.pcm") for label in CHANNELS}
        self.files = {label: open(path, "wb") for label, path in self.paths.items()}
        self.bytes = {label: 0 for label in CHANNELS}
        self.failed = False

    @classmethod
    def for_session(cls, user_id: Optional[str], capture_id: Optional[str], labels: list[str]) -> Optional["CallRecorder"]:
        """Only a two-sided call from a signed-in rep that names its recording."""
        if not user_id or not capture_id or not CAPTURE_ID.match(capture_id) or set(labels) != set(CHANNELS):
            return None
        try:
            return cls(user_id, capture_id)
        except OSError:
            logger.exception("Live recording: no temp space, this call is transcribed live only")
            return None

    def write(self, label: str, pcm: bytes) -> None:
        if self.failed or label not in self.files:
            return
        try:
            self.files[label].write(pcm)
            self.bytes[label] += len(pcm)
        except OSError:
            # Never at the cost of the call: it keeps its live transcript.
            logger.exception("Live recording: writing failed, this call is transcribed live only")
            self.failed = True

    async def finish(self, supabase: Any) -> Optional[str]:
        """Stores the session as one stereo file; returns its storage path, or None when there is nothing to keep."""
        try:
            for f in self.files.values():
                f.close()
            if self.failed or max(self.bytes.values()) < MIN_SECONDS * BYTES_PER_SECOND:
                return None
            # The two sides end a moment apart: the shorter one is filled with silence so they stay in step.
            longest = max(self.bytes.values())
            for label, size in self.bytes.items():
                if size < longest:
                    with open(self.paths[label], "ab") as f:
                        f.write(bytes(longest - size))
            ended_ms = int(time.time() * 1000)
            audio, ext, mime = await asyncio.to_thread(self._encode)
            from app.services.storage import CALL_RECORDINGS_BUCKET

            path = f"{self.user_id}/{part_name(self.capture_id, self.started_ms, ended_ms, ext)}"
            await asyncio.to_thread(
                supabase.storage.from_(CALL_RECORDINGS_BUCKET).upload,
                path=path,
                file=audio,
                file_options={"content-type": mime, "upsert": "true"},
            )
            logger.info("Live recording: stored %s (%.0f s, %d KB)", path, longest / BYTES_PER_SECOND, len(audio) // 1024)
            return path
        except Exception:
            logger.exception("Live recording: could not store the call %s; it keeps its live transcript", self.capture_id)
            return None
        finally:
            shutil.rmtree(self.dir, ignore_errors=True)

    def _encode(self) -> tuple[bytes, str, str]:
        """Opus (small, made for speech); FLAC if this ffmpeg has no Opus."""
        import subprocess

        base = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
        inputs: list[str] = []
        for label in CHANNELS:
            inputs += ["-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", "1", "-i", self.paths[label]]
        merge = ["-filter_complex", "[0:a][1:a]amerge=inputs=2[a]", "-map", "[a]", "-ac", "2"]
        for codec, ext, mime, extra in (
            ("libopus", "ogg", "audio/ogg", ["-b:a", "48k", "-application", "voip"]),
            ("flac", "flac", "audio/flac", []),
        ):
            out = os.path.join(self.dir, f"call.{ext}")
            done = subprocess.run(base + inputs + merge + ["-c:a", codec, *extra, out], capture_output=True)
            if done.returncode == 0 and os.path.exists(out):
                with open(out, "rb") as f:
                    return f.read(), ext, mime
            logger.warning("Live recording: %s encode failed: %s", codec, done.stderr.decode(errors="replace")[:300])
        raise RuntimeError("ffmpeg could not encode the call")
