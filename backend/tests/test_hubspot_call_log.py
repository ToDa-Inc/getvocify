import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.hubspot_recordings import router as hubspot_recordings_router
from app.deps import get_supabase
from app.services.hubspot.call_log import build_call_properties
from app.services.hubspot.calling_settings import recording_endpoint_url


class TestBuildCallProperties:
    def _props(self, **overrides):
        base = dict(
            occurred_at="2026-08-26T09:15:00Z",
            to_number="+34600111222",
            from_number="+34910000000",
            duration_ms=185000,
            external_id="CA0000000000000000000000000000001",
            external_account_id="hub-123",
            app_id="app-456",
            owner_id="777",
            title="Llamada Vocify",
            body="Resumen pendiente de revision.",
        )
        base.update(overrides)
        return build_call_properties(**base)

    def test_source_must_be_integrations_platform(self):
        # Without this exact value HubSpot never asks us for the recording.
        assert self._props()["hs_call_source"] == "INTEGRATIONS_PLATFORM"

    def test_carries_the_four_properties_hubspot_requires(self):
        props = self._props()
        for key in (
            "hs_call_external_id",
            "hs_call_external_account_id",
            "hs_call_app_id",
            "hs_call_source",
        ):
            assert props[key], f"{key} must be set"

    def test_duration_is_milliseconds_as_a_string(self):
        assert self._props()["hs_call_duration"] == "185000"

    def test_marks_the_call_completed(self):
        assert self._props()["hs_call_status"] == "COMPLETED"

    def test_direction_is_outbound(self):
        assert self._props()["hs_call_direction"] == "OUTBOUND"

    def test_omits_owner_when_unknown(self):
        assert "hubspot_owner_id" not in self._props(owner_id=None)

    def test_rejects_missing_external_id(self):
        with pytest.raises(ValueError):
            self._props(external_id="")


class TestRecordingEndpointUrl:
    def test_contains_the_percent_s_placeholder_hubspot_substitutes(self):
        url = recording_endpoint_url("https://api.getvocify.com")
        assert "%s" in url
        assert url.startswith("https://")

    def test_does_not_double_the_slash(self):
        assert "//public" not in recording_endpoint_url("https://api.getvocify.com/")


class FakeQuery:
    """Minimal supabase-py table().select/insert/update().eq/limit().execute() chain."""

    def __init__(self, store: list[dict]):
        self.store = store
        self._filters: list[tuple[str, object]] = []
        self._limit: int | None = None
        self._mutation: dict | None = None
        self._mutation_type: str | None = None

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
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

    def _filtered_rows(self) -> list[dict]:
        rows = list(self.store)
        for column, value in self._filters:
            rows = [r for r in rows if r.get(column) == value]
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


class TestLogCallEngagement:
    def test_writes_hubspot_hub_id_from_connection_metadata(self):
        from app.services.telephony.call_processor import log_call_engagement

        call_sid = "CA0000000000000000000000000000001"
        supabase, stores = _fake_supabase(
            {
                "outbound_calls": [
                    {
                        "twilio_call_sid": call_sid,
                        "user_id": "user-1",
                        "hubspot_contact_id": "contact-1",
                        "hubspot_deal_id": None,
                        "to_number": "+34600111222",
                        "from_number": "+34910000000",
                    }
                ],
                "crm_connections": [
                    {
                        "user_id": "user-1",
                        "provider": "hubspot",
                        "metadata": {"portal_id": "portal-999"},
                    }
                ],
            }
        )

        fake_client = MagicMock()
        captured: dict = {}

        async def fake_log_call_to_hubspot(client, *, properties, contact_id, deal_id):
            captured["properties"] = properties
            captured["contact_id"] = contact_id
            captured["deal_id"] = deal_id
            return "eng-42"

        with (
            patch(
                "app.api.crm.get_hubspot_client_from_connection",
                return_value=fake_client,
            ),
            patch(
                "app.services.hubspot.call_log.build_call_properties",
                side_effect=build_call_properties,
            ) as build_mock,
            patch(
                "app.services.hubspot.call_log.log_call_to_hubspot",
                new=AsyncMock(side_effect=fake_log_call_to_hubspot),
            ),
            patch(
                "app.services.hubspot.call_log.mark_recording_ready",
                new=AsyncMock(),
            ),
            patch(
                "app.services.telephony.call_processor.settings",
                SimpleNamespace(HUBSPOT_APP_ID="app-456"),
            ),
        ):
            asyncio.run(log_call_engagement(supabase, call_sid, 185.0))

        row = stores["outbound_calls"][0]
        assert row["hubspot_hub_id"] == "portal-999"
        assert row["hubspot_engagement_id"] == "eng-42"
        assert row["status"] == "logged"
        build_mock.assert_called_once()
        assert build_mock.call_args.kwargs["external_account_id"] == "portal-999"
        assert captured["properties"]["hs_call_external_account_id"] == "portal-999"

    def test_skips_hubspot_when_portal_id_missing(self):
        from app.services.telephony.call_processor import log_call_engagement

        call_sid = "CA0000000000000000000000000000001"
        supabase, stores = _fake_supabase(
            {
                "outbound_calls": [
                    {
                        "twilio_call_sid": call_sid,
                        "user_id": "user-1",
                        "hubspot_contact_id": "contact-1",
                        "to_number": "+34600111222",
                        "from_number": "+34910000000",
                    }
                ],
                "crm_connections": [
                    {
                        "user_id": "user-1",
                        "provider": "hubspot",
                        "metadata": {},
                    }
                ],
            }
        )

        with (
            patch("app.api.crm.get_hubspot_client_from_connection") as get_client,
            patch("app.services.hubspot.call_log.build_call_properties") as build_mock,
            patch(
                "app.services.hubspot.call_log.log_call_to_hubspot",
                new=AsyncMock(),
            ) as log_mock,
        ):
            asyncio.run(log_call_engagement(supabase, call_sid, 10.0))

        get_client.assert_not_called()
        build_mock.assert_not_called()
        log_mock.assert_not_called()
        assert "hubspot_hub_id" not in stores["outbound_calls"][0]

    def test_db_failure_does_not_propagate_to_fail_memo(self):
        """HubSpot logging is best-effort: DB errors must not bubble up."""
        from app.services.telephony.call_processor import log_call_engagement

        call_sid = "CA0000000000000000000000000000001"
        supabase, stores = _fake_supabase(
            {
                "memos": [{"id": "memo-1", "status": "extracting"}],
            }
        )

        class RaisingOutboundCallsQuery(FakeQuery):
            def execute(self):
                raise RuntimeError("outbound_calls select failed")

        def make_table(name: str):
            if name == "outbound_calls":
                return RaisingOutboundCallsQuery([])
            return FakeQuery(stores.setdefault(name, []))

        supabase.table.side_effect = make_table

        asyncio.run(log_call_engagement(supabase, call_sid, 10.0))

        assert stores["memos"][0]["status"] == "extracting"


def _recordings_client(supabase) -> TestClient:
    app = FastAPI()

    async def _get_supabase():
        return supabase

    app.dependency_overrides[get_supabase] = _get_supabase
    app.include_router(hubspot_recordings_router)
    return TestClient(app)


class TestPublicRecordingEndpoint:
    def test_openapi_lists_the_route(self):
        from app.api.router import api_router

        app = FastAPI()
        app.include_router(api_router)
        paths = app.openapi()["paths"]
        assert "/public/hubspot/recordings/{external_id}" in paths

    def test_403_when_hubspot_hub_id_is_empty(self):
        call_sid = "CA0000000000000000000000000000001"
        supabase, _ = _fake_supabase(
            {
                "outbound_calls": [
                    {
                        "twilio_call_sid": call_sid,
                        "recording_path": "user-1/rec.wav",
                        "hubspot_hub_id": None,
                    }
                ]
            }
        )
        client = _recordings_client(supabase)
        response = client.get(
            f"/public/hubspot/recordings/{call_sid}",
            params={"externalAccountId": "portal-999"},
        )
        assert response.status_code == 403

    def test_403_when_external_account_id_missing(self):
        call_sid = "CA0000000000000000000000000000001"
        supabase, _ = _fake_supabase(
            {
                "outbound_calls": [
                    {
                        "twilio_call_sid": call_sid,
                        "recording_path": "user-1/rec.wav",
                        "hubspot_hub_id": "portal-999",
                    }
                ]
            }
        )
        client = _recordings_client(supabase)
        response = client.get(f"/public/hubspot/recordings/{call_sid}")
        assert response.status_code == 403

    def test_403_when_account_ids_differ(self):
        call_sid = "CA0000000000000000000000000000001"
        supabase, _ = _fake_supabase(
            {
                "outbound_calls": [
                    {
                        "twilio_call_sid": call_sid,
                        "recording_path": "user-1/rec.wav",
                        "hubspot_hub_id": "portal-999",
                    }
                ]
            }
        )
        client = _recordings_client(supabase)
        response = client.get(
            f"/public/hubspot/recordings/{call_sid}",
            params={"externalAccountId": "other-hub"},
        )
        assert response.status_code == 403

    def test_200_with_authenticated_url_on_match(self):
        call_sid = "CA0000000000000000000000000000001"
        supabase, _ = _fake_supabase(
            {
                "outbound_calls": [
                    {
                        "twilio_call_sid": call_sid,
                        "recording_path": "user-1/rec.wav",
                        "hubspot_hub_id": "portal-999",
                    }
                ]
            }
        )
        client = _recordings_client(supabase)
        with patch(
            "app.api.hubspot_recordings.StorageService"
        ) as storage_cls:
            storage_cls.return_value.signed_call_recording_url.return_value = (
                "https://signed.example/rec.wav?token=abc"
            )
            response = client.get(
                f"/public/hubspot/recordings/{call_sid}",
                params={"externalAccountId": "portal-999"},
            )
        assert response.status_code == 200
        assert response.json() == {
            "authenticatedUrl": "https://signed.example/rec.wav?token=abc"
        }
        storage_cls.return_value.signed_call_recording_url.assert_called_once_with(
            "user-1/rec.wav", 3600
        )
