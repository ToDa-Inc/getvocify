from unittest.mock import patch

from app.services.telephony import twilio_client


def _clear():
    twilio_client._client.cache_clear()


class TestTwilioRestRegion:
    def test_ireland_account_passes_dublin_edge_and_ie1_region(self):
        _clear()
        with (
            patch("app.services.telephony.twilio_client.TwilioRestClient") as mock_cls,
            patch("app.services.telephony.twilio_client.settings") as settings,
        ):
            settings.TWILIO_ACCOUNT_SID = "AC" + "0" * 32
            settings.TWILIO_AUTH_TOKEN = "token"
            settings.TWILIO_EDGE = "dublin"
            settings.TWILIO_REGION = "ie1"
            twilio_client.twilio_rest()

        mock_cls.assert_called_once_with(
            "AC" + "0" * 32, "token", edge="dublin", region="ie1"
        )

    def test_omits_edge_and_region_when_unset(self):
        _clear()
        with (
            patch("app.services.telephony.twilio_client.TwilioRestClient") as mock_cls,
            patch("app.services.telephony.twilio_client.settings") as settings,
        ):
            settings.TWILIO_ACCOUNT_SID = "AC" + "0" * 32
            settings.TWILIO_AUTH_TOKEN = "token"
            settings.TWILIO_EDGE = None
            settings.TWILIO_REGION = None
            twilio_client.twilio_rest()

        mock_cls.assert_called_once_with("AC" + "0" * 32, "token")
