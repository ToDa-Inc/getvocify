"""Recall.ai meeting bot client (T14, D12: "el bot de Recall.ai se hace, pero solo
funciona con RECALL_API_KEY").

A bot joins a video call (Zoom/Meet/Teams) from a `meeting_url`, records and
transcribes it, then Recall calls our webhook (`bot.done`) once the transcript is
ready. We fetch the finished transcript and complete the capture through the same
path desktop captures use (`app.services.captures.complete_capture`).

Every Recall-specific assumption lives in this one block so it is easy to adjust
if Recall's contract changes later:

- Base URL: ``https://{RECALL_REGION}.recall.ai`` (default region ``eu-central-1``).
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
  ``participant.email`` is only filled for bots scheduled through Calendar V2, and only
  once Recall enables participant emails on the workspace.

Calendar V2 (Recall syncs a rep's calendar, we decide which events get a bot):

- Connect: ``POST {base}/api/v2/calendars/`` with ``platform`` (``google_calendar`` |
  ``microsoft_outlook``), ``oauth_client_id``, ``oauth_client_secret``,
  ``oauth_refresh_token``. Disconnect: ``DELETE {base}/api/v2/calendars/{id}/`` (Recall
  drops the calendar's future bots itself).
- Events: ``GET {base}/api/v2/calendar-events/?calendar_id=...&updated_at__gte=...``,
  paginated by an absolute ``next`` URL. Each event carries ``meeting_url``,
  ``start_time``, ``is_deleted``, ``bots`` and ``raw`` (the Google / Graph event).
- Schedule: ``POST {base}/api/v2/calendar-events/{id}/bot/`` with ``deduplication_key``
  and a full ``bot_config`` (Create Bot fields; meeting_url/join_at come from the event).
  Unschedule: ``DELETE`` on the same path.
- Webhooks on the same endpoint: ``calendar.sync_events`` (``calendar_id``,
  ``last_updated_ts``) and ``calendar.update`` (``calendar_id``).
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_REGION = "eu-central-1"
DEFAULT_BOT_NAME = "Vocify"

# A bot only ever needs to join a real video call - not any https URL. Zoom hosts a
# meeting on a per-tenant subdomain (*.zoom.us); Meet and Teams don't.
ALLOWED_MEETING_URL_SUFFIXES = (".zoom.us",)
ALLOWED_MEETING_URL_HOSTS = ("zoom.us", "meet.google.com", "teams.microsoft.com", "teams.live.com")


def is_allowed_meeting_url(url: str) -> bool:
    try:
        parsed = urlparse((url or "").strip())
    except Exception:
        return False
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    if host in ALLOWED_MEETING_URL_HOSTS:
        return True
    return any(host.endswith(suffix) for suffix in ALLOWED_MEETING_URL_SUFFIXES)

CREATE_BOT_PATH = "/api/v1/bot/"
BOT_DETAIL_PATH = "/api/v1/bot/{bot_id}/"
CALENDARS_PATH = "/api/v2/calendars/"
CALENDAR_DETAIL_PATH = "/api/v2/calendars/{calendar_id}/"
CALENDAR_EVENTS_PATH = "/api/v2/calendar-events/"
CALENDAR_EVENT_BOT_PATH = "/api/v2/calendar-events/{event_id}/bot/"

_TIMEOUT_SECONDS = 30.0


class RecallClientError(Exception):
    pass


def base_url_for_region(region: Optional[str]) -> str:
    r = (region or DEFAULT_REGION).strip() or DEFAULT_REGION
    return f"https://{r}.recall.ai"


def bot_config(bot_name: Optional[str] = None, metadata: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """What every Vocify bot records, whether sent by hand or scheduled from a calendar.
    `recallai_streaming: {}` is prioritize_accuracy + language_code auto: a post-call
    transcript in whatever language the call is in. Recall only accepts string metadata."""
    config: dict[str, Any] = {
        "bot_name": bot_name or DEFAULT_BOT_NAME,
        "recording_config": {"transcript": {"provider": {"recallai_streaming": {}}}},
    }
    if metadata:
        config["metadata"] = {k: str(v) for k, v in metadata.items() if v is not None}
    return config


class RecallClient:
    def __init__(self, api_key: Optional[str] = None, region: Optional[str] = None):
        self.api_key = api_key or settings.RECALL_API_KEY
        self.base_url = base_url_for_region(region or settings.RECALL_REGION)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json",
        }

    async def create_bot(
        self,
        meeting_url: str,
        bot_name: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise RecallClientError("RECALL_API_KEY is not configured")
        payload: dict[str, Any] = {"meeting_url": meeting_url, **bot_config(bot_name, metadata)}
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{self.base_url}{CREATE_BOT_PATH}", headers=self._headers(), json=payload
            )
        if response.status_code >= 400:
            raise RecallClientError(
                f"Recall create bot error {response.status_code}: {response.text[:500]}"
            )
        return response.json()

    async def delete_bot(self, bot_id: str) -> None:
        """Cancels/removes a bot that never got a capture behind it (e.g. reserve_capture
        failed after create_bot succeeded) - best-effort cleanup, not the pipeline path."""
        if not self.api_key:
            return
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            try:
                await client.delete(
                    f"{self.base_url}{BOT_DETAIL_PATH.format(bot_id=bot_id)}", headers=self._headers()
                )
            except Exception:
                logger.warning("Recall delete bot failed for %s", bot_id, exc_info=True)

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

    async def _call(self, method: str, url: str, *, what: str, **kwargs: Any) -> httpx.Response:
        if not self.api_key:
            raise RecallClientError("RECALL_API_KEY is not configured")
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.request(method, url, headers=self._headers(), **kwargs)
        if response.status_code >= 400:
            raise RecallClientError(f"Recall {what} error {response.status_code}: {response.text[:500]}")
        return response

    async def create_calendar(
        self,
        *,
        platform: str,
        oauth_client_id: str,
        oauth_client_secret: str,
        oauth_refresh_token: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "platform": platform,
            "oauth_client_id": oauth_client_id,
            "oauth_client_secret": oauth_client_secret,
            "oauth_refresh_token": oauth_refresh_token,
        }
        if metadata:
            payload["metadata"] = {k: str(v) for k, v in metadata.items() if v is not None}
        response = await self._call("POST", f"{self.base_url}{CALENDARS_PATH}", what="create calendar", json=payload)
        return response.json()

    async def get_calendar(self, calendar_id: str) -> dict[str, Any]:
        url = f"{self.base_url}{CALENDAR_DETAIL_PATH.format(calendar_id=calendar_id)}"
        return (await self._call("GET", url, what="get calendar")).json()

    async def delete_calendar(self, calendar_id: str) -> None:
        """Disconnects the calendar; Recall removes its future bots itself. Already gone
        (404) is the outcome we wanted, not an error."""
        url = f"{self.base_url}{CALENDAR_DETAIL_PATH.format(calendar_id=calendar_id)}"
        try:
            await self._call("DELETE", url, what="delete calendar")
        except RecallClientError as exc:
            if " 404:" not in str(exc):
                raise

    async def list_calendar_events(
        self,
        calendar_id: str,
        *,
        updated_at_gte: Optional[str] = None,
        start_time_gte: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        params: Optional[dict[str, str]] = {"calendar_id": calendar_id}
        if updated_at_gte:
            params["updated_at__gte"] = updated_at_gte
        if start_time_gte:
            params["start_time__gte"] = start_time_gte
        events: list[dict[str, Any]] = []
        url: Optional[str] = f"{self.base_url}{CALENDAR_EVENTS_PATH}"
        while url:
            data = (await self._call("GET", url, what="list calendar events", params=params)).json() or {}
            events.extend(data.get("results") or [])
            # `next` is an absolute URL that already carries the query: follow it as-is.
            url, params = data.get("next"), None
        return events

    async def schedule_event_bot(
        self, event_id: str, *, deduplication_key: str, config: dict[str, Any]
    ) -> dict[str, Any]:
        url = f"{self.base_url}{CALENDAR_EVENT_BOT_PATH.format(event_id=event_id)}"
        payload = {"deduplication_key": deduplication_key, "bot_config": config}
        return (await self._call("POST", url, what="schedule bot", json=payload)).json()

    async def unschedule_event_bot(self, event_id: str) -> dict[str, Any]:
        url = f"{self.base_url}{CALENDAR_EVENT_BOT_PATH.format(event_id=event_id)}"
        return (await self._call("DELETE", url, what="unschedule bot")).json()


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
    rep_email: Optional[str] = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Recall's per-participant word segments -> (plain transcript, C01 turns).

    There is no "this participant is the rep" flag from Recall. When a participant has an
    email (calendar bots with participant emails on) and we know the rep's calendar email,
    that decides it. Otherwise it is a best-effort match against the rep's own display
    name: full name-token equality or first-name equality (see `_is_rep_name_match`),
    everyone else is `prospect`. With neither to match against, the turn is `unknown`
    rather than a guess.
    """
    rep_tokens = _name_tokens(rep_name)
    rep_email_norm = (rep_email or "").strip().lower()
    turns: list[dict[str, Any]] = []
    lines: list[str] = []
    for i, segment in enumerate(segments or []):
        words = segment.get("words") or []
        text = " ".join(str(w.get("text") or "").strip() for w in words).strip()
        if not text:
            continue
        participant = segment.get("participant") or {}
        name = str(participant.get("name") or "").strip()
        email = str(participant.get("email") or "").strip().lower()

        speaker_role = "unknown"
        if rep_email_norm and email:
            speaker_role = "rep" if email == rep_email_norm else "prospect"
        elif rep_tokens:
            speaker_role = "rep" if _is_rep_name_match(rep_tokens, name) else "prospect"

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


def _name_tokens(name: Optional[str]) -> tuple[str, ...]:
    return tuple(t for t in (name or "").strip().lower().split() if t)


def _is_rep_name_match(rep_tokens: tuple[str, ...], participant_name: str) -> bool:
    """Full-name-token equality, or first-name equality - not a substring match, which
    would false-positive "Ana" against "Mariana" or "Marta" against "Martazo"."""
    if not rep_tokens or not participant_name:
        return False
    participant_tokens = _name_tokens(participant_name)
    if not participant_tokens:
        return False
    if set(participant_tokens) == set(rep_tokens):
        return True
    return participant_tokens[0] == rep_tokens[0]


def _relative_ms(timestamp: Any) -> Optional[int]:
    if not isinstance(timestamp, dict):
        return None
    relative = timestamp.get("relative")
    if not isinstance(relative, (int, float)):
        return None
    return int(relative * 1000)
