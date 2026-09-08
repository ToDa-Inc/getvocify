from __future__ import annotations

from typing import Any, Optional

import httpx

from app.config import settings

TELNYX_API = "https://api.telnyx.com/v2"


class TelnyxNotConfigured(RuntimeError):
    pass


class TelnyxClient:
    def __init__(
        self,
        *,
        api_key: str,
        connection_id: str,
        http: Optional[httpx.Client] = None,
    ) -> None:
        self.api_key = api_key
        self.connection_id = connection_id
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

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        http = self._client()
        verb = method.lower()
        caller = getattr(http, verb, None)
        if callable(caller) and verb in {"get", "post", "put", "patch", "delete"}:
            response = caller(path, **kwargs)
        else:
            response = http.request(method, path, **kwargs)
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()

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

    def mint_credential_token(self, credential_id: str) -> str:
        # Telnyx returns the JWT as a raw string body on this endpoint.
        http = self._client()
        response = http.post(f"/telephony_credentials/{credential_id}/token")
        response.raise_for_status()
        text = response.text.strip().strip('"')
        return text

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

    def dial(self, *, to: str, caller_id: str, link_to: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "connection_id": self.connection_id,
            "to": to,
            "from": caller_id,
            "link_to": link_to,
            "timeout_secs": 30,
        }
        if settings.TELNYX_OUTBOUND_VOICE_PROFILE_ID:
            payload["outbound_voice_profile_id"] = (
                settings.TELNYX_OUTBOUND_VOICE_PROFILE_ID
            )
        data = self._request("POST", "/calls", json=payload)["data"]
        return {"call_control_id": data["call_control_id"]}

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

    def hangup(self, call_control_id: str) -> None:
        self._request("POST", f"/calls/{call_control_id}/actions/hangup", json={})

    def get_recording(self, recording_id: str) -> dict[str, Any]:
        return self._request("GET", f"/recordings/{recording_id}")["data"]


def telnyx_rest() -> TelnyxClient:
    if not settings.TELNYX_API_KEY or not settings.TELNYX_CONNECTION_ID:
        raise TelnyxNotConfigured("TELNYX_API_KEY / TELNYX_CONNECTION_ID unset")
    return TelnyxClient(
        api_key=settings.TELNYX_API_KEY,
        connection_id=settings.TELNYX_CONNECTION_ID,
    )
