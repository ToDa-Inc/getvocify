"""Recall.ai meeting bot client (T14, D12: "el bot de Recall.ai se hace, pero solo
funciona con RECALL_API_KEY").

A bot joins a video call (Zoom/Meet/Teams) from a `meeting_url`, records and
transcribes it, then Recall calls our webhook (`bot.done`) once the transcript is
ready. We fetch the finished transcript and complete the capture through the same
path desktop captures use (`app.services.captures.complete_capture`).

Every Recall-specific assumption lives in this one block so it is easy to adjust
if Recall's contract changes later:

- Base URL: ``https://{RECALL_REGION}.recall.ai`` (default region ``us-west-2``).
- Create a bot: ``POST {base}/api/v1/bot/`` with
  ``{"meeting_url": ..., "bot_name": ..., "recording_config": {"transcript":
  {"provider": {"recallai_streaming": {}}}}}`` and header
  ``Authorization: Token <RECALL_API_KEY>``.
- Bot detail/status: ``GET {base}/api/v1/bot/{id}/``.
- Transcript retrieval: the bot's ``recordings[].media_shortcuts.transcript.data
  .download_url`` — a pre-signed URL Recall issues once transcription finishes,
  fetched with a plain GET (no Recall auth header).
- Webhook events: ``bot.done`` (transcript ready) and ``bot.status_change``
  (status only, no transcript yet). Signed Svix-style — see
  ``app.services.recall_webhook_signature``.
- Transcript JSON shape (assumed, Recall's documented "diarized transcript"
  format): a list of participant segments, each
  ``{"participant": {"name": "..."}, "words": [{"text": "...",
  "start_timestamp": {"relative": 0.0}, "end_timestamp": {"relative": 1.2}}]}``.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_REGION = "us-west-2"
DEFAULT_BOT_NAME = "Vocify"

CREATE_BOT_PATH = "/api/v1/bot/"
BOT_DETAIL_PATH = "/api/v1/bot/{bot_id}/"

_TIMEOUT_SECONDS = 30.0


class RecallClientError(Exception):
    pass


def base_url_for_region(region: Optional[str]) -> str:
    r = (region or DEFAULT_REGION).strip() or DEFAULT_REGION
    return f"https://{r}.recall.ai"


class RecallClient:
    def __init__(self, api_key: Optional[str] = None, region: Optional[str] = None):
        self.api_key = api_key or settings.RECALL_API_KEY
        self.base_url = base_url_for_region(region or settings.RECALL_REGION)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json",
        }

    async def create_bot(self, meeting_url: str, bot_name: Optional[str] = None) -> dict[str, Any]:
        if not self.api_key:
            raise RecallClientError("RECALL_API_KEY is not configured")
        payload: dict[str, Any] = {
            "meeting_url": meeting_url,
            "bot_name": bot_name or DEFAULT_BOT_NAME,
            "recording_config": {
                "transcript": {"provider": {"recallai_streaming": {}}},
            },
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{self.base_url}{CREATE_BOT_PATH}", headers=self._headers(), json=payload
            )
        if response.status_code >= 400:
            raise RecallClientError(
                f"Recall create bot error {response.status_code}: {response.text[:500]}"
            )
        return response.json()

    async def get_bot(self, bot_id: str) -> dict[str, Any]:
        if not self.api_key:
            raise RecallClientError("RECALL_API_KEY is not configured")
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.get(
                f"{self.base_url}{BOT_DETAIL_PATH.format(bot_id=bot_id)}", headers=self._headers()
            )
        if response.status_code >= 400:
            raise RecallClientError(
                f"Recall get bot error {response.status_code}: {response.text[:500]}"
            )
        return response.json()

    async def download_transcript(self, download_url: str) -> list[dict[str, Any]]:
        """The download_url is pre-signed by Recall; no Authorization header goes with it."""
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.get(download_url)
        if response.status_code >= 400:
            raise RecallClientError(
                f"Recall transcript download error {response.status_code}: {response.text[:500]}"
            )
        data = response.json()
        return data if isinstance(data, list) else []


def transcript_download_url_from_bot(bot: dict[str, Any]) -> Optional[str]:
    """The first recording that already has a transcript download URL. None while
    transcription is still running - the caller should treat that as 'not ready yet',
    not as an error."""
    for recording in bot.get("recordings") or []:
        shortcuts = (recording or {}).get("media_shortcuts") or {}
        transcript = shortcuts.get("transcript") or {}
        data = transcript.get("data") or {}
        url = data.get("download_url")
        if url:
            return str(url)
    return None


def turns_from_recall_transcript(
    segments: list[dict[str, Any]],
    *,
    rep_name: Optional[str] = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Recall's per-participant word segments -> (plain transcript, C01 turns).

    speaker_role is a best-effort match against the rep's own display name (there is
    no reliable "this participant is the rep" flag from Recall): a participant whose
    name contains the rep's name is `rep`, everyone else is `prospect`. Without a
    rep_name to match against, every turn is `unknown` rather than a guess.
    """
    needle = (rep_name or "").strip().lower()
    turns: list[dict[str, Any]] = []
    lines: list[str] = []
    for i, segment in enumerate(segments or []):
        words = segment.get("words") or []
        text = " ".join(str(w.get("text") or "").strip() for w in words).strip()
        if not text:
            continue
        participant = segment.get("participant") or {}
        name = str(participant.get("name") or "").strip()

        speaker_role = "unknown"
        if needle:
            speaker_role = "rep" if name and needle in name.lower() else "prospect"

        start_ms = _relative_ms(words[0].get("start_timestamp")) if words else None
        end_ms = _relative_ms(words[-1].get("end_timestamp")) if words else None

        turns.append({
            "id": f"recall-{i}",
            "speaker_role": speaker_role,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "text": text,
            "is_final": True,
        })
        lines.append(f"{name}: {text}" if name else text)
    return "\n".join(lines), turns


def _relative_ms(timestamp: Any) -> Optional[int]:
    if not isinstance(timestamp, dict):
        return None
    relative = timestamp.get("relative")
    if not isinstance(relative, (int, float)):
        return None
    return int(relative * 1000)
