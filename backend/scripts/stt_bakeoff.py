#!/usr/bin/env python3
"""Compare Vocify STT paths on recent memos.

Providers:
  - deepgram_nova3       — production batch (STT_PROVIDER=deepgram)
  - speechmatics_batch   — batch fallback (Standard operating point)
  - speechmatics_rt      — live WebSocket path (Enhanced, memo mode)
  - gemini_3_5_transcribe — OpenRouter google/gemini-3.5-transcribe

Usage (from backend/):
  .venv/bin/python scripts/stt_bakeoff.py
  .venv/bin/python scripts/stt_bakeoff.py --limit 5
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import os
import re
import subprocess
import sys
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
import websockets

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

# Repo root .env wins for shared keys (OpenRouter credits live there).
load_dotenv(".env")
load_dotenv("../.env", override=True)

from app.config import settings
from app.services.memo_playback import recording_path_for_memo
from app.services.session_entities import (
    resolve_batch_language,
    resolve_profile_stt_languages,
    speechmatics_batch_language,
    speechmatics_rt_ws_language,
)
from app.services.speechmatics_batch import SpeechmaticsBatchService, batch_transcription_config
from app.services.stt_batch import (
    _transcribe_speechmatics,
    transcribe_audio,
    use_channel_stt,
    wav_channel_count,
)
from app.services.storage import StorageService
from supabase import create_client

logger = logging.getLogger(__name__)

REPORT_DIR = Path(__file__).resolve().parent.parent / "evals" / "stt" / "reports"
GEMINI_MODEL = "google/gemini-3.5-transcribe"
OPENROUTER_STT_URL = "https://openrouter.ai/api/v1/audio/transcriptions"
RT_CHUNK_BYTES = 6400  # 200ms @ 16kHz mono s16le


@dataclass
class ProviderResult:
    provider: str
    text: str = ""
    latency_sec: float = 0.0
    error: Optional[str] = None
    confidence: Optional[float] = None
    char_count: int = 0
    word_count: int = 0
    similarity_to_raw: Optional[float] = None
    similarity_to_sanitized: Optional[float] = None
    cost_usd: Optional[float] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


@dataclass
class MemoBakeoff:
    memo_id: str
    source: str
    duration_sec: float
    language: str
    channels: int
    reference_raw_len: int
    reference_sanitized_len: int
    production_provider: str
    results: dict[str, ProviderResult] = field(default_factory=dict)


_SPEAKER_PREFIX = re.compile(
    r"^(?:s\d+|speaker\s*:?\s*(?:channel_\d+|s\d+))\s*:?\s*",
    re.IGNORECASE | re.MULTILINE,
)


def _strip_speakers(text: str) -> str:
    lines = []
    for line in (text or "").splitlines():
        cleaned = _SPEAKER_PREFIX.sub("", line.strip())
        if cleaned:
            lines.append(cleaned)
    return " ".join(lines)


def _normalize(text: str) -> str:
    text = _strip_speakers(text)
    text = unicodedata.normalize("NFKD", text.lower())
    text = re.sub(r"[^a-z0-9áéíóúüñ\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _similarity(a: str, b: str) -> float:
    na, nb = _normalize(a), _normalize(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def _word_stats(text: str) -> tuple[int, int]:
    t = (text or "").strip()
    return len(t), len(t.split())


def _content_type_for_path(path: str) -> str:
    ext = Path(path).suffix.lower()
    return {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".ogg": "audio/ogg",
        ".webm": "audio/webm",
        ".m4a": "audio/mp4",
    }.get(ext, "audio/wav")


def _audio_format_from_bytes(audio: bytes, path: str = "") -> tuple[str, str]:
    ct = _content_type_for_path(path)
    if ct == "audio/wav":
        return "wav", ct
    if "webm" in ct:
        return "webm", ct
    if "mpeg" in ct:
        return "mp3", ct
    if "ogg" in ct:
        return "ogg", ct
    return "wav", ct


def _wav_to_pcm_16k_mono(audio: bytes) -> bytes:
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "s16le",
            "pipe:1",
        ],
        input=audio,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout:
        raise RuntimeError(f"ffmpeg pcm conversion failed: {proc.stderr.decode()[:300]}")
    return proc.stdout


def _profile_languages(memo: dict[str, Any]) -> list[str]:
    return resolve_profile_stt_languages(user_id=str(memo.get("user_id") or ""))


def _dominant_language_from_raw(memo: dict[str, Any]) -> str:
    """Best-effort pin from stored raw transcript (production may have re-pinned)."""
    raw = (memo.get("transcript_raw") or memo.get("transcript") or "").lower()
    ca_hits = len(re.findall(r"\b(d'acord|escoltes|t'escolto|alumne|vostra|m'agradaria)\b", raw))
    es_hits = len(re.findall(r"\b(de acuerdo|escuchas|te escucho|alumno|vuestra|me gustaría)\b", raw))
    if ca_hits > es_hits:
        return "ca"
    if es_hits > ca_hits:
        return "es"
    return resolve_batch_language(user_id=str(memo.get("user_id") or ""))


async def _download_memo_audio(supabase: Any, memo: dict[str, Any]) -> tuple[bytes, str]:
    path = recording_path_for_memo(memo, supabase)
    if path:
        data = StorageService(supabase).download_call_recording(path)
        return data, path
    url = (memo.get("audio_url") or "").strip()
    if not url:
        raise RuntimeError("no recording_path or audio_url")
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        parsed = urlparse(url)
        return resp.content, parsed.path or "audio.webm"


async def transcribe_deepgram_production(
    audio: bytes,
    *,
    content_type: str,
    user_id: str,
    source: str,
) -> ProviderResult:
    """Full production batch path: Deepgram + language re-pin + glossary."""
    t0 = time.perf_counter()
    try:
        result = await transcribe_audio(
            audio,
            content_type=content_type,
            user_id=user_id or None,
            diarization=True,
            source=source,
        )
        chars, words = _word_stats(result.text)
        return ProviderResult(
            provider="deepgram_nova3",
            text=result.text,
            latency_sec=time.perf_counter() - t0,
            confidence=result.confidence,
            char_count=chars,
            word_count=words,
        )
    except Exception as e:
        return ProviderResult(
            provider="deepgram_nova3",
            latency_sec=time.perf_counter() - t0,
            error=str(e),
        )


async def transcribe_speechmatics_batch(
    audio: bytes,
    *,
    content_type: str,
    profile_langs: list[str],
    user_id: str,
    multichannel: bool,
) -> ProviderResult:
    t0 = time.perf_counter()
    try:
        sm_lang, sm_lang_id = speechmatics_batch_language(profile_langs)
        result = await _transcribe_speechmatics(
            audio,
            content_type=content_type,
            sm_lang=sm_lang,
            sm_lang_id=sm_lang_id,
            user_id=user_id or None,
            extra_terms=None,
            diarization=not multichannel,
            t0=t0,
            multichannel=multichannel,
        )
        chars, words = _word_stats(result.text)
        return ProviderResult(
            provider="speechmatics_batch",
            text=result.text,
            latency_sec=time.perf_counter() - t0,
            char_count=chars,
            word_count=words,
        )
    except Exception as e:
        return ProviderResult(
            provider="speechmatics_batch",
            latency_sec=time.perf_counter() - t0,
            error=str(e),
        )


async def transcribe_speechmatics_rt(
    audio: bytes,
    *,
    profile_langs: list[str],
    pin_language: str,
) -> ProviderResult:
    """Replay file audio through Speechmatics RT (Enhanced, memo mode)."""
    api_key = (settings.SPEECHMATICS_API_KEY or "").strip()
    if not api_key:
        return ProviderResult(provider="speechmatics_rt", error="SPEECHMATICS_API_KEY missing")

    t0 = time.perf_counter()
    try:
        pcm = _wav_to_pcm_16k_mono(audio)
    except Exception as e:
        return ProviderResult(provider="speechmatics_rt", latency_sec=time.perf_counter() - t0, error=str(e))

    lang = speechmatics_rt_ws_language(pin_language, profile_languages=profile_langs)
    url = f"wss://eu2.rt.speechmatics.com/v2/{lang}"
    finals: list[str] = []

    config = {
        "message": "StartRecognition",
        "audio_format": {"type": "raw", "encoding": "pcm_s16le", "sample_rate": 16000},
        "transcription_config": {
            "language": lang,
            "operating_point": "enhanced",
            "enable_partials": False,
            "max_delay": 1.5,
            "max_delay_mode": "flexible",
            "diarization": "none",
        },
    }

    try:
        async with websockets.connect(
            url,
            additional_headers={"Authorization": f"Bearer {api_key}"},
            open_timeout=30,
        ) as ws:
            await ws.send(json.dumps(config))
            started = asyncio.Event()

            async def sender() -> None:
                await started.wait()
                for i in range(0, len(pcm), RT_CHUNK_BYTES):
                    await ws.send(pcm[i : i + RT_CHUNK_BYTES])
                    await asyncio.sleep(0.05)
                await ws.send(json.dumps({"message": "EndOfStream", "last_seq_no": 0}))

            async def receiver() -> None:
                async for message in ws:
                    data = json.loads(message)
                    msg_type = data.get("message")
                    if msg_type == "RecognitionStarted":
                        started.set()
                    elif msg_type == "AddTranscript":
                        text = (data.get("metadata") or {}).get("transcript", "").strip()
                        if text:
                            finals.append(text)
                    elif msg_type == "Error":
                        raise RuntimeError(data.get("reason") or "Speechmatics RT error")
                    elif msg_type == "EndOfTranscript":
                        break

            await asyncio.gather(sender(), receiver())
        text = " ".join(finals).strip()
        chars, words = _word_stats(text)
        return ProviderResult(
            provider="speechmatics_rt",
            text=text,
            latency_sec=time.perf_counter() - t0,
            char_count=chars,
            word_count=words,
        )
    except Exception as e:
        return ProviderResult(
            provider="speechmatics_rt",
            latency_sec=time.perf_counter() - t0,
            error=str(e),
        )


async def transcribe_gemini(
    audio: bytes,
    *,
    path: str,
    language: str,
) -> ProviderResult:
    api_key = (settings.OPENROUTER_API_KEY or "").strip()
    if not api_key:
        return ProviderResult(provider="gemini_3_5_transcribe", error="OPENROUTER_API_KEY missing")

    fmt, _ = _audio_format_from_bytes(audio, path)
    t0 = time.perf_counter()
    payload = {
        "model": GEMINI_MODEL,
        "input_audio": {"data": base64.b64encode(audio).decode("ascii"), "format": fmt},
        "language": language,
        "response_format": "json",
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://getvocify.com",
        "X-OpenRouter-Title": "Vocify STT Bakeoff",
    }
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(OPENROUTER_STT_URL, headers=headers, json=payload)
            if resp.status_code >= 400:
                raise RuntimeError(f"OpenRouter {resp.status_code}: {resp.text[:500]}")
            data = resp.json()
        text = str(data.get("text") or data.get("transcript") or "").strip()
        if not text and isinstance(data.get("choices"), list):
            text = str((data["choices"][0] or {}).get("text") or "").strip()
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        chars, words = _word_stats(text)
        return ProviderResult(
            provider="gemini_3_5_transcribe",
            text=text,
            latency_sec=time.perf_counter() - t0,
            char_count=chars,
            word_count=words,
            cost_usd=float(usage.get("cost") or 0) or None,
            input_tokens=int(usage["input_tokens"]) if usage.get("input_tokens") is not None else None,
            output_tokens=int(usage["output_tokens"]) if usage.get("output_tokens") is not None else None,
        )
    except Exception as e:
        return ProviderResult(
            provider="gemini_3_5_transcribe",
            latency_sec=time.perf_counter() - t0,
            error=str(e),
        )


async def run_memo(
    supabase: Any,
    memo: dict[str, Any],
    *,
    skip_providers: set[str],
) -> MemoBakeoff:
    memo_id = str(memo["id"])
    source = (memo.get("source") or memo.get("source_type") or "").strip()
    profile_langs = _profile_languages(memo)
    pin_language = _dominant_language_from_raw(memo)
    raw_ref = memo.get("transcript_raw") or ""
    sanitized_ref = memo.get("transcript") or ""
    meta = memo.get("transcript_stt_meta") or {}

    audio, path = await _download_memo_audio(supabase, memo)
    content_type = _content_type_for_path(path)
    multichannel = use_channel_stt(audio, source=source)
    channels = wav_channel_count(audio)

    bakeoff = MemoBakeoff(
        memo_id=memo_id,
        source=source,
        duration_sec=float(memo.get("audio_duration") or 0),
        language=f"{pin_language} (profile={','.join(profile_langs)})",
        channels=channels,
        reference_raw_len=len(raw_ref),
        reference_sanitized_len=len(sanitized_ref),
        production_provider=str(meta.get("provider") or "unknown"),
    )

    tasks: dict[str, asyncio.Task[ProviderResult]] = {}
    user_id = str(memo.get("user_id") or "")
    if "deepgram_nova3" not in skip_providers:
        tasks["deepgram_nova3"] = asyncio.create_task(
            transcribe_deepgram_production(
                audio,
                content_type=content_type,
                user_id=user_id,
                source=source,
            )
        )
    if "speechmatics_batch" not in skip_providers:
        tasks["speechmatics_batch"] = asyncio.create_task(
            transcribe_speechmatics_batch(
                audio,
                content_type=content_type,
                profile_langs=profile_langs,
                user_id=user_id,
                multichannel=multichannel,
            )
        )
    if "speechmatics_rt" not in skip_providers:
        tasks["speechmatics_rt"] = asyncio.create_task(
            transcribe_speechmatics_rt(
                audio,
                profile_langs=profile_langs,
                pin_language=pin_language,
            )
        )
    if "gemini_3_5_transcribe" not in skip_providers:
        tasks["gemini_3_5_transcribe"] = asyncio.create_task(
            transcribe_gemini(audio, path=path, language=pin_language)
        )

    for name, task in tasks.items():
        result = await task
        if result.text:
            result.similarity_to_raw = _similarity(result.text, raw_ref)
            result.similarity_to_sanitized = _similarity(result.text, sanitized_ref)
        bakeoff.results[name] = result
        status = "OK" if not result.error else f"ERR: {result.error[:80]}"
        print(
            f"  {name}: {status} "
            f"({result.latency_sec:.1f}s, sim_raw={result.similarity_to_raw}, words={result.word_count})"
        )

    return bakeoff


def _aggregate(bakeoffs: list[MemoBakeoff]) -> dict[str, Any]:
    providers = ["deepgram_nova3", "speechmatics_batch", "speechmatics_rt", "gemini_3_5_transcribe"]
    summary: dict[str, Any] = {}
    for provider in providers:
        rows = [b.results.get(provider) for b in bakeoffs if provider in b.results]
        ok = [r for r in rows if r and not r.error and r.text]
        errs = [r for r in rows if r and r.error]
        if not rows:
            continue
        costs = [r.cost_usd for r in ok if r.cost_usd is not None]
        summary[provider] = {
            "attempts": len(rows),
            "success": len(ok),
            "errors": len(errs),
            "avg_latency_sec": round(sum(r.latency_sec for r in ok) / max(len(ok), 1), 2),
            "avg_similarity_to_raw": round(
                sum(r.similarity_to_raw or 0 for r in ok) / max(len(ok), 1), 4
            ),
            "avg_similarity_to_sanitized": round(
                sum(r.similarity_to_sanitized or 0 for r in ok) / max(len(ok), 1), 4
            ),
            "avg_word_count": round(sum(r.word_count for r in ok) / max(len(ok), 1), 1),
            "total_cost_usd": round(sum(costs), 4) if costs else None,
        }
    return summary


def _markdown_report(bakeoffs: list[MemoBakeoff], summary: dict[str, Any]) -> str:
    lines = [
        f"# STT bake-off — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"Memos tested: {len(bakeoffs)} (>30s, with stored audio)",
        "",
        "## Aggregate (similarity vs production `transcript_raw` / sanitized `transcript`)",
        "",
        "| Provider | OK | Avg latency | Sim→raw | Sim→sanitized | Avg words | Total cost |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for provider, stats in summary.items():
        cost = stats.get("total_cost_usd")
        cost_s = f"${cost:.4f}" if cost is not None else "—"
        lines.append(
            f"| {provider} | {stats['success']}/{stats['attempts']} | "
            f"{stats['avg_latency_sec']}s | {stats['avg_similarity_to_raw']} | "
            f"{stats['avg_similarity_to_sanitized']} | {stats['avg_word_count']} | {cost_s} |"
        )
    lines.extend(["", "## Per memo", ""])
    for b in bakeoffs:
        lines.append(
            f"### {b.memo_id[:8]}… — {b.source}, {b.duration_sec:.0f}s, lang={b.language}, ch={b.channels}"
        )
        for name, r in b.results.items():
            if r.error:
                lines.append(f"- **{name}**: ERROR — {r.error}")
            else:
                lines.append(
                    f"- **{name}**: {r.latency_sec:.1f}s, sim_raw={r.similarity_to_raw:.3f}, "
                    f"sim_san={r.similarity_to_sanitized:.3f}, {r.word_count} words"
                )
        lines.append("")
    return "\n".join(lines)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--skip", nargs="*", default=[], help="Provider ids to skip")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    res = (
        supabase.table("memos")
        .select(
            "id,user_id,audio_duration,recording_path,audio_url,source,source_type,"
            "transcript,transcript_raw,transcript_stt_meta,created_at,status"
        )
        .gt("audio_duration", 30)
        .order("created_at", desc=True)
        .limit(max(args.limit * 2, 40))
        .execute()
    )
    memos = [
        m
        for m in (res.data or [])
        if (m.get("recording_path") or m.get("audio_url"))
    ][: args.limit]

    if not memos:
        print("No memos found with audio.", file=sys.stderr)
        return 1

    print(f"Running STT bake-off on {len(memos)} memos…")
    print(f"Batch SM config: {batch_transcription_config(language='es', diarization=True)['operating_point']}")

    bakeoffs: list[MemoBakeoff] = []
    skip = set(args.skip)
    for i, memo in enumerate(memos, 1):
        print(f"\n[{i}/{len(memos)}] memo {memo['id'][:8]}… ({memo.get('source')}, {memo.get('audio_duration')}s)")
        try:
            bakeoffs.append(await run_memo(supabase, memo, skip_providers=skip))
        except Exception as e:
            print(f"  SKIP memo: {e}")

    summary = _aggregate(bakeoffs)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")
    json_path = REPORT_DIR / f"{stamp}-stt-bakeoff.json"
    md_path = REPORT_DIR / f"{stamp}-stt-bakeoff.md"

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "memo_count": len(bakeoffs),
        "summary": summary,
        "memos": [
            {
                **{k: v for k, v in asdict(b).items() if k != "results"},
                "results": {k: asdict(v) for k, v in b.results.items()},
            }
            for b in bakeoffs
        ],
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    md_path.write_text(_markdown_report(bakeoffs, summary))

    print("\n=== SUMMARY ===")
    for provider, stats in summary.items():
        cost = stats.get("total_cost_usd")
        cost_s = f", cost ${cost:.4f}" if cost is not None else ""
        print(
            f"{provider}: {stats['success']}/{stats['attempts']} ok, "
            f"avg latency {stats['avg_latency_sec']}s, "
            f"sim→raw {stats['avg_similarity_to_raw']}, "
            f"sim→sanitized {stats['avg_similarity_to_sanitized']}{cost_s}"
        )
    print(f"\nReports: {json_path}\n         {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
