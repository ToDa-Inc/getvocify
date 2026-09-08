"""Park-and-bridge Telnyx voice webhook.

Fixture envelope matches Telnyx Voice API webhooks (`call.initiated` +
`state=parked`) with `custom_headers` and `from` = SIP username.
"""

from __future__ import annotations

import base64
import copy
import json
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import nacl.encoding
import nacl.signing
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import webhooks
from app.api.webhooks import router as webhooks_router
from app.services.telephony.telnyx_client import TelnyxClient

USER_ID = "11111111-1111-1111-1111-111111111111"
SIP_USERNAME = "userabc"
PARKED_ID = "v3:parked-leg"
PSTN_ID = "v3:pstn-leg"
VERIFIED_CLI = "+34910000000"
PROSPECT = "+34600111222"

# Telnyx outbound-dialer / Voice API envelope: parked WebRTC leg.
PARKED_INITIATED = {
    "data": {
        "record_type": "event",
        "event_type": "call.initiated",
        "id": "0ccc7b54-4df3-4bca-a65a-3da1ecc777f0",
        "occurred_at": "2018-02-02T22:25:27.521992Z",
        "payload": {
            "call_control_id": PARKED_ID,
            "connection_id": "7267xxxxxxxxxxxxxx",
            "call_leg_id": "d14dbcee-880b-11eb-8204-02420a0f7568",
            "call_session_id": "428c31b6-abf3-3bc1-b7f4-5013ef9657c1",
            "client_state": None,
            "from": SIP_USERNAME,
            "to": PROSPECT,
            "direction": "incoming",
            "state": "parked",
            "custom_headers": [
                {
                    "header_name": "X-Vocify-Caller-Id",
                    "header_value": VERIFIED_CLI,
                },
                {
                    "header_name": "X-Vocify-Contact-Id",
                    "header_value": "123",
                },
                {
                    "header_name": "X-Vocify-Deal-Id",
                    "header_value": "456",
                },
            ],
        },
    },
    "meta": {
        "attempt": 1,
        "delivered_to": "https://api.getvocify.com/webhooks/telnyx/voice",
    },
}

PSTN_ANSWERED = {
    "data": {
        "record_type": "event",
        "event_type": "call.answered",
        "id": "1ddd8c65-5ef4-4cdb-b76b-4eb2fdd888f1",
        "occurred_at": "2018-02-02T22:25:29.000000Z",
        "payload": {
            "call_control_id": PSTN_ID,
            "connection_id": "7267xxxxxxxxxxxxxx",
            "call_leg_id": "e25eccff-990c-22fc-9315-13531b1f8679",
            "call_session_id": "428c31b6-abf3-3bc1-b7f4-5013ef9657c1",
            "from": VERIFIED_CLI,
            "to": PROSPECT,
            "direction": "outgoing",
        },
    },
    "meta": {"attempt": 1, "delivered_to": "https://api.getvocify.com/webhooks/telnyx/voice"},
}


class FakeQuery:
    """Minimal supabase-py chain; includes JSONB `contains` for provider_state."""

    def __init__(self, store: list[dict]):
        self.store = store
        self._filters: list[tuple[str, object]] = []
        self._contains: list[tuple[str, object]] = []
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._mutation: dict | None = None
        self._mutation_type: str | None = None

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def contains(self, column, value):
        self._contains.append((column, value))
        return self

    def order(self, column, desc=False, **_k):
        self._order = (column, desc)
        return self

    def limit(self, n, *_a, **_k):
        self._limit = n
        return self

    def insert(self, row):
        self._mutation_type = "insert"
        self._mutation = row
        return self

    def update(self, row):
        self._mutation_type = "update"
        self._mutation = row
        return self

    def _matches(self, row: dict) -> bool:
        for column, value in self._filters:
            if row.get(column) != value:
                return False
        for column, value in self._contains:
            cell = row.get(column)
            if not isinstance(cell, dict) or not isinstance(value, dict):
                return False
            if any(cell.get(k) != v for k, v in value.items()):
                return False
        return True

    def _filtered_rows(self) -> list[dict]:
        rows = [r for r in self.store if self._matches(r)]
        if self._order is not None:
            column, desc = self._order
            rows = sorted(
                rows, key=lambda r: (r.get(column) is None, r.get(column)), reverse=desc
            )
        if self._limit is not None:
            rows = rows[: self._limit]
        return rows

    def execute(self):
        if self._mutation_type == "update":
            matched = self._filtered_rows()
            for row in matched:
                row.update(self._mutation or {})
            return SimpleNamespace(data=list(matched))
        if self._mutation_type == "insert":
            row = dict(self._mutation or {})
            self.store.append(row)
            return SimpleNamespace(data=[row])
        return SimpleNamespace(data=self._filtered_rows())


def _fake_supabase(tables: dict[str, list[dict]]):
    stores: dict[str, list[dict]] = {
        name: [dict(r) for r in rows] for name, rows in tables.items()
    }

    def make_table(name: str) -> FakeQuery:
        return FakeQuery(stores.setdefault(name, []))

    client = MagicMock()
    client.table.side_effect = make_table
    return client, stores


def _keys():
    signing = nacl.signing.SigningKey.generate()
    pub = signing.verify_key.encode(encoder=nacl.encoding.HexEncoder).decode()
    return signing, pub


def _signed_headers(signing, body: bytes) -> dict[str, str]:
    timestamp = str(int(time.time()))
    signature = base64.b64encode(
        signing.sign(f"{timestamp}|".encode() + body).signature
    ).decode()
    return {
        "telnyx-timestamp": timestamp,
        "telnyx-signature-ed25519": signature,
        "content-type": "application/json",
    }


def _test_client() -> TestClient:
    app = FastAPI()
    app.include_router(webhooks_router, prefix="/webhooks")
    return TestClient(app)


def _event_body(event: dict) -> bytes:
    return json.dumps(event, separators=(",", ":")).encode("utf-8")


def _parked(*, to: str | None = None, sip: str | None = None, headers=None) -> dict:
    event = copy.deepcopy(PARKED_INITIATED)
    payload = event["data"]["payload"]
    if to is not None:
        payload["to"] = to
    if sip is not None:
        payload["from"] = sip
    if headers is not None:
        payload["custom_headers"] = headers
    return event


def _credential_tables(*, caller_ids=None):
    tables = {
        "user_telephony_credentials": [
            {
                "user_id": USER_ID,
                "provider": "telnyx",
                "sip_username": SIP_USERNAME,
            }
        ],
        "user_caller_ids": caller_ids
        if caller_ids is not None
        else [
            {
                "user_id": USER_ID,
                "phone_number": VERIFIED_CLI,
                "status": "verified",
                "is_default": True,
            }
        ],
    }
    return tables


def _post(event: dict, *, signing, pub: str, supabase, telnyx, **setting_overrides):
    body = _event_body(event)
    settings = {
        "TELNYX_PUBLIC_KEY": pub,
        "CALLING_DEFAULT_COUNTRY_CODE": "34",
        "CALLING_RECORDING_ANNOUNCEMENT_ENABLED": False,
        **setting_overrides,
    }
    with (
        patch("app.api.webhooks.get_supabase", return_value=supabase),
        patch("app.api.webhooks.telnyx_rest", return_value=telnyx, create=True),
        patch.multiple(webhooks.settings, **settings),
    ):
        return _test_client().post(
            "/webhooks/telnyx/voice",
            content=body,
            headers=_signed_headers(signing, body),
        )


class TestTelnyxVoiceSignature:
    def test_bad_signature_is_forbidden_and_does_not_dial(self):
        signing, pub = _keys()
        supabase, stores = _fake_supabase(_credential_tables())
        telnyx = MagicMock()
        body = _event_body(PARKED_INITIATED)
        with (
            patch("app.api.webhooks.get_supabase", return_value=supabase),
            patch("app.api.webhooks.telnyx_rest", return_value=telnyx, create=True),
            patch.object(webhooks.settings, "TELNYX_PUBLIC_KEY", pub),
        ):
            resp = _test_client().post(
                "/webhooks/telnyx/voice",
                content=body,
                headers={
                    "telnyx-timestamp": str(int(time.time())),
                    "telnyx-signature-ed25519": "not-a-real-signature",
                    "content-type": "application/json",
                },
            )

        assert resp.status_code == 403
        telnyx.dial.assert_not_called()
        assert stores.get("outbound_calls", []) == []


class TestTelnyxParkedInitiated:
    def test_unknown_sip_hangs_up_parked_and_does_not_insert(self):
        signing, pub = _keys()
        supabase, stores = _fake_supabase({})
        telnyx = MagicMock()

        resp = _post(PARKED_INITIATED, signing=signing, pub=pub, supabase=supabase, telnyx=telnyx)

        assert resp.status_code == 204
        telnyx.hangup.assert_called_once_with(PARKED_ID)
        telnyx.dial.assert_not_called()
        assert stores.get("outbound_calls", []) == []

    def test_emergency_to_hangs_up_and_does_not_dial(self):
        signing, pub = _keys()
        supabase, stores = _fake_supabase(_credential_tables())
        telnyx = MagicMock()

        resp = _post(
            _parked(to="112"),
            signing=signing,
            pub=pub,
            supabase=supabase,
            telnyx=telnyx,
        )

        assert resp.status_code == 204
        telnyx.hangup.assert_called_once_with(PARKED_ID)
        telnyx.dial.assert_not_called()
        assert stores.get("outbound_calls", []) == []

    def test_unverified_cli_hangs_up_and_does_not_dial(self):
        signing, pub = _keys()
        supabase, stores = _fake_supabase(
            _credential_tables(
                caller_ids=[
                    {
                        "user_id": "22222222-2222-2222-2222-222222222222",
                        "phone_number": "+34699999999",
                        "status": "verified",
                    }
                ]
            )
        )
        telnyx = MagicMock()

        resp = _post(
            _parked(
                headers=[
                    {
                        "header_name": "X-Vocify-Caller-Id",
                        "header_value": "+34699999999",
                    }
                ]
            ),
            signing=signing,
            pub=pub,
            supabase=supabase,
            telnyx=telnyx,
        )

        assert resp.status_code == 204
        telnyx.hangup.assert_called_once_with(PARKED_ID)
        telnyx.dial.assert_not_called()
        assert stores.get("outbound_calls", []) == []

    def test_happy_parked_inserts_and_dials_resolved_cli_without_bridge_intent(self):
        signing, pub = _keys()
        supabase, stores = _fake_supabase(_credential_tables())
        http = MagicMock()
        http.post.return_value.status_code = 200
        http.post.return_value.content = b'{"data":{"call_control_id":"v3:pstn-leg"}}'
        http.post.return_value.json.return_value = {
            "data": {"call_control_id": PSTN_ID}
        }
        http.post.return_value.raise_for_status = lambda: None
        telnyx = TelnyxClient(api_key="KEY", connection_id="CONN", http=http)

        resp = _post(PARKED_INITIATED, signing=signing, pub=pub, supabase=supabase, telnyx=telnyx)

        assert resp.status_code == 204
        body = http.post.call_args.kwargs["json"]
        assert body["from"] == VERIFIED_CLI
        assert body["to"] == PROSPECT
        assert body["link_to"] == PARKED_ID
        assert "bridge_intent" not in body
        row = stores["outbound_calls"][0]
        assert row["carrier"] == "telnyx"
        assert row["carrier_call_id"] == PARKED_ID
        assert row["from_number"] == VERIFIED_CLI
        assert row["to_number"] == PROSPECT
        assert row["hubspot_contact_id"] == "123"
        assert row["hubspot_deal_id"] == "456"
        assert row["hubspot_hub_id"] is None
        assert row["provider_state"] == {"parked_id": PARKED_ID, "pstn_id": PSTN_ID}

    def test_sip_uri_from_still_resolves_to_credential_user(self):
        signing, pub = _keys()
        supabase, stores = _fake_supabase(_credential_tables())
        telnyx = MagicMock()
        telnyx.dial.return_value = {"call_control_id": PSTN_ID}

        resp = _post(
            _parked(sip="sip:userabc@sip.telnyx.com"),
            signing=signing,
            pub=pub,
            supabase=supabase,
            telnyx=telnyx,
        )

        assert resp.status_code == 204
        telnyx.hangup.assert_not_called()
        telnyx.dial.assert_called_once()
        assert telnyx.dial.call_args.kwargs["caller_id"] == VERIFIED_CLI
        assert telnyx.dial.call_args.kwargs["link_to"] == PARKED_ID
        assert stores["outbound_calls"][0]["user_id"] == USER_ID

    def test_dial_failure_after_insert_hangs_up_parked(self):
        signing, pub = _keys()
        supabase, stores = _fake_supabase(_credential_tables())
        telnyx = MagicMock()
        telnyx.dial.side_effect = RuntimeError("telnyx dial failed")

        resp = _post(PARKED_INITIATED, signing=signing, pub=pub, supabase=supabase, telnyx=telnyx)

        assert resp.status_code == 204
        telnyx.hangup.assert_called_once_with(PARKED_ID)
        assert stores["outbound_calls"][0]["carrier_call_id"] == PARKED_ID
        assert stores["outbound_calls"][0]["provider_state"] == {"parked_id": PARKED_ID}


class TestTelnyxAnsweredBridge:
    def test_answered_announcement_off_bridges_dual_wav(self):
        signing, pub = _keys()
        supabase, _ = _fake_supabase(
            {
                "outbound_calls": [
                    {
                        "user_id": USER_ID,
                        "carrier": "telnyx",
                        "carrier_call_id": PARKED_ID,
                        "status": "dialing",
                        "provider_state": {"parked_id": PARKED_ID, "pstn_id": PSTN_ID},
                    }
                ]
            }
        )
        http = MagicMock()
        http.post.return_value.status_code = 200
        http.post.return_value.content = b""
        http.post.return_value.raise_for_status = lambda: None
        telnyx = TelnyxClient(api_key="KEY", connection_id="CONN", http=http)

        resp = _post(
            PSTN_ANSWERED,
            signing=signing,
            pub=pub,
            supabase=supabase,
            telnyx=telnyx,
            CALLING_RECORDING_ANNOUNCEMENT_ENABLED=False,
        )

        assert resp.status_code == 204
        path = http.post.call_args.args[0]
        assert path == f"/calls/{PARKED_ID}/actions/bridge"
        body = http.post.call_args.kwargs["json"]
        assert body["call_control_id"] == PSTN_ID
        assert body["record"] == "record-from-answer"
        assert body["record_channels"] == "dual"
        assert body["record_format"] == "wav"
