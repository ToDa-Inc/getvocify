import pytest

from app.services.hubspot.call_log import (
    hubspot_call_body_for_disposition,
    hubspot_call_status_for_disposition,
    log_call_to_hubspot,
    normalize_twilio_dial_status,
)
from app.services.hubspot.exceptions import HubSpotValidationError


class _FakeHubSpot:
    def __init__(self, posts):
        self.posts = []
        self.puts = []
        self._posts = list(posts)

    async def post(self, endpoint, data=None):
        self.posts.append((endpoint, data))
        result = self._posts.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    async def put(self, endpoint, data=None):
        self.puts.append((endpoint, data))
        return {}


PROPS = {"hs_call_title": "Llamada Vocify"}


class TestCallLogDisposition:
    def test_normalize_twilio_dial_status(self):
        assert normalize_twilio_dial_status("no-answer") == "no_answer"
        assert normalize_twilio_dial_status("busy") == "busy"
        assert normalize_twilio_dial_status("completed") == "connected"

    def test_hubspot_status_mapping(self):
        assert hubspot_call_status_for_disposition("busy") == "BUSY"
        assert hubspot_call_status_for_disposition("connected") == "COMPLETED"
        assert hubspot_call_status_for_disposition("voicemail") == "COMPLETED"

    def test_hubspot_body_mapping(self):
        assert "Buzon de voz" in hubspot_call_body_for_disposition("voicemail")
        assert hubspot_call_body_for_disposition("no_answer") == "Sin respuesta."


class TestLogCallToHubspot:
    @pytest.mark.asyncio
    async def test_creates_call_with_contact_type_194_in_one_request(self):
        client = _FakeHubSpot([{"id": "519607244993"}])

        engagement_id = await log_call_to_hubspot(
            client,
            properties=PROPS,
            contact_id="755172251846",
            deal_id=None,
        )

        assert engagement_id == "519607244993"
        assert len(client.posts) == 1
        assert client.puts == []
        endpoint, data = client.posts[0]
        assert endpoint == "/crm/v3/objects/calls"
        assert data["properties"] == PROPS
        assert data["associations"] == [
            {
                "to": {"id": "755172251846"},
                "types": [
                    {
                        "associationCategory": "HUBSPOT_DEFINED",
                        "associationTypeId": 194,
                    }
                ],
            }
        ]

    @pytest.mark.asyncio
    async def test_includes_deal_type_206_when_deal_id_is_set(self):
        client = _FakeHubSpot([{"id": "1"}])

        await log_call_to_hubspot(
            client,
            properties=PROPS,
            contact_id="755",
            deal_id="99",
        )

        types = [
            item["types"][0]["associationTypeId"]
            for item in client.posts[0][1]["associations"]
        ]
        assert types == [194, 206]

    @pytest.mark.asyncio
    async def test_omits_associations_when_no_records(self):
        client = _FakeHubSpot([{"id": "1"}])

        await log_call_to_hubspot(
            client, properties=PROPS, contact_id=None, deal_id=None
        )

        assert "associations" not in client.posts[0][1]
        assert client.puts == []

    @pytest.mark.asyncio
    async def test_retries_bare_create_then_v4_default_associate(self):
        client = _FakeHubSpot(
            [
                HubSpotValidationError("bad association", status_code=400),
                {"id": "519607244993"},
            ]
        )

        engagement_id = await log_call_to_hubspot(
            client,
            properties=PROPS,
            contact_id="755172251846",
            deal_id=None,
        )

        assert engagement_id == "519607244993"
        assert client.posts[1][1] == {"properties": PROPS}
        assert "associations" not in client.posts[1][1]
        assert client.puts == [
            (
                "/crm/v4/objects/call/519607244993/associations/default/contact/755172251846",
                None,
            )
        ]
