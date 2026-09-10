from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

TELNYX_API = "https://api.telnyx.com/v2"
RINGBACK_PATH = "/static/call-ringback.wav"


def ringback_audio_url() -> str | None:
    override = (getattr(settings, "TELNYX_RINGBACK_URL", None) or "").strip()
    if override:
        return override
    base = (settings.BACKEND_PUBLIC_URL or "").rstrip("/")
    if not base:
        return None
    return f"{base}{RINGBACK_PATH}"


class TelnyxNotConfigured(RuntimeError):
    pass


class TelnyxClient:
    def __init__(
        self,
        *,
        api_key: str,
        connection_id: str,
        call_control_app_id: Optional[str] = None,
        http: Optional[httpx.Client] = None,
    ) -> None:
        self.api_key = api_key
        self.connection_id = connection_id
        self.call_control_app_id = call_control_app_id or connection_id
        self._http = http

    def _client(self) -> httpx.Client:
        if self._http is not None:
            return self._http
        return httpx.Client(
            base_url=TELNYX_API,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    def _borrow_http(self) -> tuple[httpx.Client, bool]:
        if self._http is not None:
            return self._http, False
        return self._client(), True

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        http, owned = self._borrow_http()
        try:
            verb = method.lower()
            caller = getattr(http, verb, None)
            if callable(caller) and verb in {"get", "post", "put", "patch", "delete"}:
                response = caller(path, **kwargs)
            else:
                response = http.request(method, path, **kwargs)
            if getattr(response, "status_code", 0) >= 400:
                detail = (getattr(response, "text", None) or "").strip()
                raise httpx.HTTPStatusError(
                    f"{response.status_code} {getattr(response, 'reason_phrase', '')} "
                    f"for {getattr(response, 'url', '')}"
                    + (f": {detail}" if detail else ""),
                    request=getattr(response, "request", None),
                    response=response,
                )
            if not response.content:
                return {}
            return response.json()
        finally:
            if owned:
                http.close()

    def create_telephony_credential(self, name: str) -> dict[str, Any]:
        data = self._request(
            "POST",
            "/telephony_credentials",
            json={"connection_id": self.connection_id, "name": name[:100]},
        )["data"]
        return {
            "credential_id": data["id"],
            "sip_username": data["sip_username"],
        }

    def delete_telephony_credential(self, credential_id: str) -> None:
        self._request("DELETE", f"/telephony_credentials/{credential_id}")

    def mint_credential_token(self, credential_id: str) -> str:
        # Telnyx returns the JWT as a raw string body on this endpoint.
        http, owned = self._borrow_http()
        try:
            response = http.post(f"/telephony_credentials/{credential_id}/token")
            response.raise_for_status()
            return response.text.strip().strip('"')
        finally:
            if owned:
                http.close()

    def create_verified_number(self, phone_number: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/verified_numbers",
            json={"phone_number": phone_number, "verification_method": "call"},
        )

    def verify_number_code(self, phone_number: str, code: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/verified_numbers/{phone_number}/actions/verify",
            json={"verification_code": code},
        )

    def _dial_payload(self, *, to: str, caller_id: str, link_to: str) -> dict[str, Any]:
        # Telnyx CLI policy reads the SIP user-part, highest first: PPI, PAI,
        # RPID, FROM. EEA still wants a dialable CLI in PAI — the user-part is
        # the +E164. Do not set `bridge_intent` (it overwrites `from`).
        sip_uri = f"<sip:{caller_id}@sip.telnyx.com>"
        payload: dict[str, Any] = {
            "connection_id": self.call_control_app_id,
            "to": to,
            "from": caller_id,
            "privacy": "none",
            "link_to": link_to,
            "timeout_secs": 30,
            # UDP is the Dial default. Identity is not sent over UDP.
            "sip_transport_protocol": "TLS",
            "custom_headers": [
                {"name": "P-Preferred-Identity", "value": sip_uri},
                {"name": "P-Asserted-Identity", "value": sip_uri},
                {"name": "Remote-Party-Id", "value": sip_uri},
            ],
        }
        if settings.TELNYX_OUTBOUND_VOICE_PROFILE_ID:
            payload["outbound_voice_profile_id"] = (
                settings.TELNYX_OUTBOUND_VOICE_PROFILE_ID
            )
        return payload

    def dial(self, *, to: str, caller_id: str, link_to: str) -> dict[str, Any]:
        payload = self._dial_payload(to=to, caller_id=caller_id, link_to=link_to)
        logger.info(
            "Telnyx dial from=%s to=%s tls=1 ovp=%s",
            caller_id,
            to,
            bool(payload.get("outbound_voice_profile_id")),
        )
        try:
            data = self._request("POST", "/calls", json=payload)["data"]
        except httpx.HTTPStatusError as exc:
            if (
                exc.response is None
                or exc.response.status_code != 422
                or "sip_transport_protocol" not in payload
            ):
                raise
            logger.warning("Telnyx Dial TLS rejected; retrying UDP")
            payload = dict(payload)
            payload.pop("sip_transport_protocol", None)
            data = self._request("POST", "/calls", json=payload)["data"]
        return {"call_control_id": data["call_control_id"]}

    def answer(self, call_control_id: str) -> None:
        try:
            self._request(
                "POST",
                f"/calls/{call_control_id}/actions/answer",
                json={},
            )
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code in (422, 404):
                logger.warning("Telnyx answer ignored for %s", call_control_id)
                return
            raise

    def playback_start(
        self, call_control_id: str, audio_url: str, *, loop: str = "1"
    ) -> None:
        try:
            self._request(
                "POST",
                f"/calls/{call_control_id}/actions/playback_start",
                json={"audio_url": audio_url, "loop": loop},
            )
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code in (422, 404):
                logger.warning(
                    "Telnyx playback_start ignored for %s", call_control_id
                )
                return
            raise

    def playback_stop(self, call_control_id: str) -> None:
        try:
            self._request(
                "POST",
                f"/calls/{call_control_id}/actions/playback_stop",
                json={},
            )
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code in (422, 404):
                logger.warning(
                    "Telnyx playback_stop ignored for %s", call_control_id
                )
                return
            raise

    def speak(self, call_control_id: str, payload: str) -> None:
        self._request(
            "POST",
            f"/calls/{call_control_id}/actions/speak",
            json={"payload": payload, "language": "es-ES", "voice": "female"},
        )

    def bridge(self, parked_id: str, pstn_id: str) -> None:
        self._request(
            "POST",
            f"/calls/{parked_id}/actions/bridge",
            json={
                "call_control_id": pstn_id,
                "record": "record-from-answer",
                "record_channels": "dual",
                "record_format": "wav",
            },
        )

    def hangup(self, call_control_id: str, cause: Optional[str] = None) -> None:
        body: dict[str, Any] = {}
        if cause:
            body["cause"] = cause
        try:
            self._request(
                "POST", f"/calls/{call_control_id}/actions/hangup", json=body
            )
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code == 422:
                logger.warning("Telnyx hangup ignored for ended call %s", call_control_id)
                return
            raise

    def get_recording(self, recording_id: str) -> dict[str, Any]:
        return self._request("GET", f"/recordings/{recording_id}")["data"]


def telnyx_rest() -> TelnyxClient:
    if not settings.TELNYX_API_KEY or not settings.TELNYX_CONNECTION_ID:
        raise TelnyxNotConfigured("TELNYX_API_KEY / TELNYX_CONNECTION_ID unset")
    return TelnyxClient(
        api_key=settings.TELNYX_API_KEY,
        connection_id=settings.TELNYX_CONNECTION_ID,
        call_control_app_id=settings.TELNYX_CALL_CONTROL_APP_ID,
    )
