"""A desktop call's memo is written from the whole call, not from its live transcript.

The live service keeps each session's audio (live_recording.py). When the desktop sends the finished call, this waits
for that recording, transcribes it whole with the file STT (MAI-2: rep on channel 0, the other side on channel 1) and
hands back that transcript. Anything missing or failing gives None, and the memo keeps its live transcript: a call is
never lost or held up for good by this.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

# The live service stores the last session a few seconds after the rep hangs up; long calls take longer to encode.
WAIT_S = 90.0
POLL_S = 2.0
# A session that ended this long before the call was sent is not its last one.
LAST_SESSION_SLACK_MS = 60_000
# A whole-call transcript far shorter than the live one means the recording missed part of the call.
MIN_WORD_RATIO = 0.5

_PART = re.compile(r"^live-(?P<capture>[A-Za-z0-9-]+)-(?P<start>\d{13})-(?P<end>\d{13})\.(?P<ext>ogg|flac)$")
MIMES = {"ogg": "audio/ogg", "flac": "audio/flac"}


@dataclass
class WholeCall:
    transcript: str
    recording_path: str
    model: Optional[str]
    seconds: float


def _parts(supabase: Any, user_id: str, capture_id: str) -> list[dict]:
    from app.services.storage import CALL_RECORDINGS_BUCKET

    rows = supabase.storage.from_(CALL_RECORDINGS_BUCKET).list(user_id, {"search": f"live-{capture_id}-", "limit": 100})
    parts = []
    for row in rows or []:
        m = _PART.match(str(row.get("name") or ""))
        if m and m.group("capture") == capture_id:
            parts.append({"path": f"{user_id}/{row['name']}", "start": int(m.group("start")), "end": int(m.group("end")), "ext": m.group("ext")})
    return sorted(parts, key=lambda p: p["start"])


async def wait_for_recording(supabase: Any, user_id: str, capture_id: str, sent_at_ms: int, *, wait_s: Optional[float] = None) -> list[dict]:
    """The call's sessions, once the last one (ended around when the call was sent) is stored; [] after wait_s."""
    deadline = time.monotonic() + (WAIT_S if wait_s is None else wait_s)
    while True:
        try:
            parts = await asyncio.to_thread(_parts, supabase, user_id, capture_id)
        except Exception:
            logger.warning("Desktop recording: could not list %s", capture_id, exc_info=True)
            parts = []
        if parts and parts[-1]["end"] >= sent_at_ms - LAST_SESSION_SLACK_MS:
            return parts
        if time.monotonic() >= deadline:
            if parts:
                logger.warning("Desktop recording: %s has no session ending near when it was sent; using what there is", capture_id)
            return parts
        await asyncio.sleep(POLL_S)


def _download(supabase: Any, path: str) -> bytes:
    from app.services.storage import StorageService

    return StorageService(supabase).download_call_recording(path)


def _join(blobs: list[tuple[bytes, str]]) -> tuple[bytes, str]:
    """Sessions of one call, one after the other, in one file (same codec, so no re-encoding)."""
    if len(blobs) == 1:
        return blobs[0]
    work = tempfile.mkdtemp(prefix="vocify-join-")
    try:
        ext = blobs[0][1]
        listing = os.path.join(work, "parts.txt")
        with open(listing, "w") as f:
            for i, (data, part_ext) in enumerate(blobs):
                if part_ext != ext:
                    raise RuntimeError("sessions of one call in different formats")
                path = os.path.join(work, f"{i}.{ext}")
                with open(path, "wb") as p:
                    p.write(data)
                f.write(f"file '{path}'\n")
        out = os.path.join(work, f"call.{ext}")
        done = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", listing, "-c", "copy", out],
            capture_output=True,
        )
        if done.returncode != 0:
            raise RuntimeError(done.stderr.decode(errors="replace")[:300])
        with open(out, "rb") as f:
            return f.read(), ext
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _words(text: str) -> int:
    return len(re.findall(r"\w+", re.sub(r"SPEAKER:\s*S\d+", " ", text or "")))


async def whole_call_transcript(
    supabase: Any, *, user_id: str, capture_id: str, sent_at_ms: int, live_transcript: str
) -> Optional[WholeCall]:
    """The call transcribed whole, or None (no recording, a failure, or a recording that missed part of the call)."""
    parts = await wait_for_recording(supabase, user_id, capture_id, sent_at_ms)
    if not parts:
        logger.info("Desktop recording: none for %s; the memo keeps its live transcript", capture_id)
        return None
    try:
        blobs = [(await asyncio.to_thread(_download, supabase, p["path"]), p["ext"]) for p in parts]
        audio, ext = await asyncio.to_thread(_join, blobs)
        path = parts[0]["path"]
        if len(parts) > 1:
            from app.services.storage import CALL_RECORDINGS_BUCKET

            path = f"{user_id}/live-{capture_id}-call.{ext}"
            await asyncio.to_thread(
                supabase.storage.from_(CALL_RECORDINGS_BUCKET).upload,
                path=path, file=audio, file_options={"content-type": MIMES[ext], "upsert": "true"},
            )
        from app.services.stt_batch import transcribe_audio

        stt = await transcribe_audio(
            audio, content_type=MIMES[ext], user_id=user_id, diarization=True, source="desktop_call", rep_channel=0
        )
    except Exception:
        logger.exception("Desktop recording: whole-call transcription of %s failed; the memo keeps its live transcript", capture_id)
        return None
    text = (stt.text or "").strip()
    live_words, whole_words = _words(live_transcript), _words(text)
    if not text or (live_words >= 30 and whole_words < live_words * MIN_WORD_RATIO):
        logger.warning(
            "Desktop recording: %s whole-call transcript has %d words against %d live; keeping the live one",
            capture_id, whole_words, live_words,
        )
        return None
    seconds = sum(p["end"] - p["start"] for p in parts) / 1000
    logger.info("Desktop recording: %s transcribed whole (%d words, live had %d)", capture_id, whole_words, live_words)
    return WholeCall(transcript=text, recording_path=path, model=getattr(stt, "model", None), seconds=seconds)
