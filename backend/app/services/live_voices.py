"""Who is speaking on the other side of a live call, told apart by their voices.

A small speaker model (ECAPA-TDNN, int8, run with onnxruntime) turns a second or two of speech into 192 numbers; two
clips of one voice land close together, two voices apart. VoiceBook keeps one profile per voice heard in the call and
puts each new piece of speech on the closest one, or starts a new voice when none is close. Nothing outlives the call:
the profiles are voiceprints of people who never agreed to be kept, so they live in memory and go with the session.

Measured on 12 recorded calls (two voices each, from the mixed audio): 99% of pieces on the right voice at
NEW_BELOW 0.30..0.35. In a made-up meeting of 3..6 different people the same threshold split a person in two now
and then (about 1.5 voices per person at 0.40) and merged two people at 0.30, which is why the client can merge two
voices and move a line to another (merge, move).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
BYTES_PER_SECOND = SAMPLE_RATE * 2
# A shorter piece does not hold enough of a voice to tell it from another ("sí", "mm").
MIN_SPEECH_S = 1.5
# The start of a longer piece is enough; the rest only costs time.
MAX_SPEECH_S = 8.0
# Cosine similarity to the closest voice under which a piece is a voice not heard before ...
NEW_BELOW = 0.35
# ... and over which it is that voice for sure; in between it is the closest one, but only a guess.
SURE_ABOVE = 0.50
# A call has this many voices at most; past it a piece goes to the closest one.
MAX_VOICES = 8

N_FFT = 400
HOP = 160
N_MELS = 80
DEFAULT_MODEL = Path(__file__).resolve().parents[2] / "models" / "voice_embedding_int8.onnx"


def _mel(hz: np.ndarray | float) -> np.ndarray | float:
    return 2595 * np.log10(1 + np.asarray(hz) / 700)


def _hz(mel: np.ndarray) -> np.ndarray:
    return 700 * (10 ** (mel / 2595) - 1)


def _filterbank() -> np.ndarray:
    """Triangular mel filters, (N_FFT // 2 + 1, N_MELS): the ones the model was trained with (SpeechBrain's Fbank)."""
    edges = _hz(np.linspace(_mel(0.0), _mel(SAMPLE_RATE / 2), N_MELS + 2))
    centre, band = edges[1:-1], (edges[1:] - edges[:-1])[:-1]
    slope = (np.linspace(0, SAMPLE_RATE // 2, N_FFT // 2 + 1)[None, :] - centre[:, None]) / band[:, None]
    return np.maximum(0, np.minimum(slope + 1, -slope + 1)).T.astype(np.float32)


_FILTERS = _filterbank()
_WINDOW = np.hamming(N_FFT + 1)[:-1].astype(np.float32)


def fbank(wav: np.ndarray) -> np.ndarray:
    """Log-mel features of 16 kHz mono audio in [-1, 1], (frames, N_MELS), each band minus its mean over the piece."""
    x = np.pad(wav.astype(np.float32), (N_FFT // 2, N_FFT // 2))
    frames = 1 + (len(x) - N_FFT) // HOP
    at = np.arange(N_FFT)[None, :] + HOP * np.arange(frames)[:, None]
    spectrum = np.fft.rfft(x[at] * _WINDOW, axis=1)
    db = 10 * np.log10(np.maximum((spectrum.real**2 + spectrum.imag**2) @ _FILTERS, 1e-10))
    db = np.maximum(db, db.max() - 80.0)
    return (db - db.mean(axis=0, keepdims=True)).astype(np.float32)


class VoiceEmbedder:
    """The speaker model. Loaded on first use and shared by every call; a run is thread-safe, and one thread each keeps
    a call's voices from taking the machine from the others."""

    def __init__(self, model_path: Optional[Path | str] = None) -> None:
        self.path = Path(model_path) if model_path else DEFAULT_MODEL
        self._session = None
        self._lock = threading.Lock()

    def available(self) -> bool:
        return self.path.is_file()

    def _load(self):
        with self._lock:
            if self._session is None:
                import onnxruntime as ort

                options = ort.SessionOptions()
                options.intra_op_num_threads = 1
                self._session = ort.InferenceSession(str(self.path), options, providers=["CPUExecutionProvider"])
            return self._session

    def embed(self, pcm: bytes) -> Optional[np.ndarray]:
        """The unit-length voiceprint of 16 kHz mono int16 audio, or None when there is too little speech."""
        seconds = len(pcm) / BYTES_PER_SECOND
        if seconds < MIN_SPEECH_S:
            return None
        samples = np.frombuffer(pcm, dtype=np.int16, count=len(pcm) // 2)[: int(MAX_SPEECH_S * SAMPLE_RATE)]
        out = self._load().run(None, {"feats": fbank(samples.astype(np.float32) / 32768.0)[None]})[0].reshape(-1)
        norm = float(np.linalg.norm(out))
        return out / norm if norm > 0 else None


@dataclass
class Voice:
    id: int
    total: np.ndarray  # the sum of its pieces' voiceprints: the direction is the voice's profile
    pieces: int = 0
    seconds: float = 0.0


@dataclass(frozen=True)
class Heard:
    voice: int
    sure: bool  # False when the piece was only close enough to be the voice, not clearly it


class VoiceBook:
    """The voices of one call, in the order they were first heard (1, 2, ...)."""

    def __init__(self) -> None:
        self.voices: dict[int, Voice] = {}
        self._next = 1
        # Every piece kept by where it started, so a line can be moved to another voice.
        self._pieces: dict[float, tuple[np.ndarray, float, int]] = {}

    def _new(self, print_: np.ndarray) -> Voice:
        voice = Voice(self._next, np.zeros_like(print_))
        self.voices[voice.id] = voice
        self._next += 1
        return voice

    def _add(self, voice: Voice, print_: np.ndarray, seconds: float) -> None:
        voice.total = voice.total + print_
        voice.pieces += 1
        voice.seconds += seconds

    def _remove(self, voice: Voice, print_: np.ndarray, seconds: float) -> None:
        voice.pieces -= 1
        voice.seconds -= seconds
        if voice.pieces <= 0:
            del self.voices[voice.id]
        else:
            voice.total = voice.total - print_

    def _closest(self, print_: np.ndarray) -> tuple[Optional[Voice], float]:
        best, best_sim = None, -1.0
        for voice in self.voices.values():
            norm = float(np.linalg.norm(voice.total))
            sim = float(voice.total @ print_) / norm if norm > 0 else -1.0
            if sim > best_sim:
                best, best_sim = voice, sim
        return best, best_sim

    def hear(self, key: float, print_: np.ndarray, seconds: float) -> Heard:
        """Puts a piece (kept under `key`, where it started) on the closest voice, or on a new one."""
        closest, sim = self._closest(print_)
        if closest is None or (sim < NEW_BELOW and len(self.voices) < MAX_VOICES):
            voice, sure = self._new(print_), True
        else:
            voice, sure = closest, sim >= SURE_ABOVE
        self._add(voice, print_, seconds)
        self._pieces[key] = (print_, seconds, voice.id)
        return Heard(voice.id, sure)

    def merge(self, keep: int, drop: int) -> bool:
        """Two voices that are one person: `drop` becomes `keep`, its past pieces and the ones to come."""
        if keep == drop or keep not in self.voices or drop not in self.voices:
            return False
        kept, dropped = self.voices[keep], self.voices.pop(drop)
        kept.total = kept.total + dropped.total
        kept.pieces += dropped.pieces
        kept.seconds += dropped.seconds
        self._pieces = {k: (p, s, keep if v == drop else v) for k, (p, s, v) in self._pieces.items()}
        return True

    def move(self, key: float, voice: Optional[int]) -> Optional[int]:
        """A line the rep says is someone else's: it goes to voice `voice`, or to a new one when that is None. Returns
        the voice it is on now, or None when the piece or the voice is unknown."""
        piece = self._pieces.get(key)
        if piece is None or (voice is not None and voice not in self.voices):
            return None
        print_, seconds, old = piece
        if voice == old:
            return old
        if old in self.voices:
            self._remove(self.voices[old], print_, seconds)
        target = self._new(print_) if voice is None else self.voices[voice]
        self._add(target, print_, seconds)
        self._pieces[key] = (print_, seconds, target.id)
        return target.id
