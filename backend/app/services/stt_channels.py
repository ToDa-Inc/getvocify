"""Speechmatics realtime channel diarization (source labeling).

Docs: https://docs.speechmatics.com/speech-to-text/realtime/realtime-diarization
SaaS max 2 channels. Audio is sent with AddChannelAudio, not mixed PCM.
"""

from __future__ import annotations

from typing import Any, Optional

COPILOT_CHANNEL_MODE = "copilot_channels"
ALLOWED_CHANNEL_LABELS = ("prospect", "rep")


def parse_channel_labels(raw: Optional[str]) -> list[str]:
    if not raw or not str(raw).strip():
        return ["prospect", "rep"]
    labels: list[str] = []
    for part in str(raw).split(","):
        p = part.strip().lower()
        if p in ALLOWED_CHANNEL_LABELS and p not in labels:
            labels.append(p)
        if len(labels) == 2:
            break
    return labels or ["prospect"]


def transcription_diarization_for_mode(
    mode: str,
    *,
    channel_labels: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Diarization keys for Speechmatics transcription_config (not the full config)."""
    if mode == COPILOT_CHANNEL_MODE:
        labels = channel_labels or ["prospect", "rep"]
        return {
            "diarization": "channel",
            "channel_diarization_labels": labels,
        }
    if mode in ("enroll", "copilot"):
        return {"diarization": "speaker"}
    return {"diarization": "none"}


def sm_add_channel_audio(channel: str, data_b64: str) -> dict[str, str]:
    return {
        "message": "AddChannelAudio",
        "channel": channel,
        "data": data_b64,
    }


def client_text_to_sm_item(
    data: dict[str, Any],
    allowed_channels: list[str],
) -> dict[str, Any] | str | None:
    msg_type = data.get("type") or data.get("message")
    if msg_type == "AddChannelAudio":
        channel = data.get("channel")
        raw = data.get("data")
        if channel not in allowed_channels or not isinstance(raw, str) or not raw:
            return None
        return sm_add_channel_audio(str(channel), raw)
    if msg_type in ("Finalize", "ForceEndOfUtterance"):
        item: dict[str, Any] = {"message": "ForceEndOfUtterance"}
        channel = data.get("channel")
        if channel in allowed_channels:
            item["channel"] = channel
        return item
    if msg_type == "CloseStream":
        return "close"
    return None


def speechmatics_audio_channel(data: dict[str, Any]) -> Optional[str]:
    ch = data.get("channel")
    if isinstance(ch, str) and ch in ALLOWED_CHANNEL_LABELS:
        return ch
    return None


def accepts_client_pcm_bytes(mode: str) -> bool:
    """Channel sessions must not mix raw PCM into AddChannelAudio streams."""
    return mode != COPILOT_CHANNEL_MODE


def _offset_ms(value: Any, offset_s: float = 0.0) -> int | None:
    if value is None:
        return None
    return int(round((float(value) + offset_s) * 1000))


def speechmatics_words(data: dict, offset_s: float = 0.0) -> list[dict[str, Any]]:
    """Pull word-level content + speaker from Speechmatics results[]; times shifted by `offset_s`."""
    words: list[dict[str, Any]] = []
    for item in data.get("results") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") not in (None, "word"):
            # Keep punctuation attached as text without speaker votes
            if item.get("type") == "punctuation":
                alts = item.get("alternatives") or []
                content = (alts[0] or {}).get("content") if alts else None
                if content:
                    words.append({"text": str(content), "speaker": None, "is_punct": True})
            continue
        alts = item.get("alternatives") or []
        if not alts:
            continue
        alt = alts[0] if isinstance(alts[0], dict) else {}
        content = alt.get("content")
        if not content:
            continue
        speaker = alt.get("speaker")
        words.append(
            {
                "text": str(content),
                "speaker": str(speaker) if speaker else None,
                "is_punct": False,
                "start_ms": _offset_ms(item.get("start_time"), offset_s),
                "end_ms": _offset_ms(item.get("end_time"), offset_s),
            }
        )
    return words
