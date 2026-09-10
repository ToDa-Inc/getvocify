from unittest.mock import MagicMock, patch

from app.services.telephony.telnyx_client import TelnyxClient


def test_dial_posts_from_chosen_by_server():
    http = MagicMock()
    http.post.return_value.status_code = 200
    http.post.return_value.json.return_value = {
        "data": {"call_control_id": "v3:pstn"}
    }
    http.post.return_value.raise_for_status = lambda: None
    client = TelnyxClient(
        api_key="KEY",
        connection_id="CRED_CONN",
        call_control_app_id="CC_APP",
        http=http,
    )
    result = client.dial(
        to="+34600111222",
        caller_id="+34600999888",
        link_to="v3:parked",
    )
    assert result["call_control_id"] == "v3:pstn"
    body = http.post.call_args.kwargs["json"]
    assert body["from"] == "+34600999888"
    assert body["to"] == "+34600111222"
    assert body["connection_id"] == "CC_APP"
    assert body["privacy"] == "none"
    assert body["sip_transport_protocol"] == "TLS"
    assert "bridge_intent" not in body
    assert body["link_to"] == "v3:parked"
    assert body["custom_headers"] == [
        {"name": "P-Preferred-Identity", "value": "<sip:+34600999888@sip.telnyx.com>"},
        {"name": "P-Asserted-Identity", "value": "<sip:+34600999888@sip.telnyx.com>"},
        {"name": "Remote-Party-Id", "value": "<sip:+34600999888@sip.telnyx.com>"},
    ]


def test_dial_retries_without_tls_when_telnyx_returns_422():
    bad = MagicMock()
    bad.status_code = 422
    bad.reason_phrase = "Unprocessable Entity"
    bad.url = "https://api.telnyx.com/v2/calls"
    bad.text = '{"errors":[{"code":"10015"}]}'
    bad.request = MagicMock()
    good = MagicMock()
    good.status_code = 200
    good.content = b'{"data":{"call_control_id":"v3:pstn"}}'
    good.json.return_value = {"data": {"call_control_id": "v3:pstn"}}
    http = MagicMock()
    http.post.side_effect = [bad, good]
    client = TelnyxClient(
        api_key="KEY",
        connection_id="CRED_CONN",
        call_control_app_id="CC_APP",
        http=http,
    )
    result = client.dial(
        to="+34600111222",
        caller_id="+34600999888",
        link_to="v3:parked",
    )
    assert result["call_control_id"] == "v3:pstn"
    assert http.post.call_count == 2
    first = http.post.call_args_list[0].kwargs["json"]
    second = http.post.call_args_list[1].kwargs["json"]
    assert first["sip_transport_protocol"] == "TLS"
    assert "sip_transport_protocol" not in second
    assert second["from"] == "+34600999888"


def test_owned_http_client_is_closed_after_request():
    response = MagicMock()
    response.status_code = 200
    response.content = b'{"data":{"call_control_id":"v3:pstn"}}'
    response.json.return_value = {"data": {"call_control_id": "v3:pstn"}}
    response.raise_for_status = lambda: None
    owned = MagicMock()
    owned.post.return_value = response
    with patch(
        "app.services.telephony.telnyx_client.httpx.Client",
        return_value=owned,
    ):
        client = TelnyxClient(api_key="KEY", connection_id="CONN")
        client.dial(to="+34600111222", caller_id="+34600999888", link_to="v3:parked")
    owned.close.assert_called_once()
    owned.post.assert_called_once()


def test_playback_start_plays_ringback_once_on_parked_leg():
    http = MagicMock()
    http.post.return_value.status_code = 200
    http.post.return_value.content = b""
    http.post.return_value.raise_for_status = lambda: None
    client = TelnyxClient(api_key="KEY", connection_id="CONN", http=http)
    client.playback_start("v3:parked", "https://api.example/static/call-ringback.wav")
    path, = http.post.call_args.args
    assert path == "/calls/v3:parked/actions/playback_start"
    assert http.post.call_args.kwargs["json"] == {
        "audio_url": "https://api.example/static/call-ringback.wav",
        "loop": "1",
    }


def test_playback_stop_ignores_already_ended_422():
    http = MagicMock()
    response = MagicMock()
    response.status_code = 422
    response.reason_phrase = "Unprocessable Entity"
    response.url = "https://api.telnyx.com/v2/calls/v3:x/actions/playback_stop"
    response.text = '{"errors":[{"code":"90018"}]}'
    response.request = MagicMock()
    http.post.return_value = response
    client = TelnyxClient(api_key="KEY", connection_id="CONN", http=http)
    client.playback_stop("v3:x")
    http.post.assert_called_once()


def test_ringback_audio_url_prefers_override():
    from app.services.telephony.telnyx_client import ringback_audio_url

    with patch("app.services.telephony.telnyx_client.settings") as settings:
        settings.TELNYX_RINGBACK_URL = "https://cdn.example/ring.wav"
        settings.BACKEND_PUBLIC_URL = "https://api.getvocify.com"
        assert ringback_audio_url() == "https://cdn.example/ring.wav"
        settings.TELNYX_RINGBACK_URL = ""
        assert ringback_audio_url() == (
            "https://api.getvocify.com/static/call-ringback.wav"
        )


def test_answer_ignores_already_answered_422():
    http = MagicMock()
    response = MagicMock()
    response.status_code = 422
    response.reason_phrase = "Unprocessable Entity"
    response.url = "https://api.telnyx.com/v2/calls/v3:x/actions/answer"
    response.text = '{"errors":[{"code":"90018"}]}'
    response.request = MagicMock()
    http.post.return_value = response
    client = TelnyxClient(api_key="KEY", connection_id="CONN", http=http)
    client.answer("v3:x")
    http.post.assert_called_once()


def test_hangup_sends_cause_for_parked_busy():
    http = MagicMock()
    http.post.return_value.status_code = 200
    http.post.return_value.content = b""
    http.post.return_value.raise_for_status = lambda: None
    client = TelnyxClient(api_key="KEY", connection_id="CONN", http=http)
    client.hangup("v3:parked", cause="USER_BUSY")
    path, = http.post.call_args.args
    assert path == "/calls/v3:parked/actions/hangup"
    assert http.post.call_args.kwargs["json"] == {"cause": "USER_BUSY"}


def test_hangup_ignores_already_ended_422():
    http = MagicMock()
    response = MagicMock()
    response.status_code = 422
    response.reason_phrase = "Unprocessable Entity"
    response.url = "https://api.telnyx.com/v2/calls/v3:x/actions/hangup"
    response.text = '{"errors":[{"code":"10015"}]}'
    response.is_error = True
    response.request = MagicMock()
    http.post.return_value = response
    client = TelnyxClient(api_key="KEY", connection_id="CONN", http=http)
    client.hangup("v3:x")
    http.post.assert_called_once()


def test_delete_telephony_credential_uses_rest_path():
    http = MagicMock()
    http.delete.return_value.status_code = 200
    http.delete.return_value.content = b""
    http.delete.return_value.raise_for_status = lambda: None
    client = TelnyxClient(api_key="KEY", connection_id="CONN", http=http)
    client.delete_telephony_credential("cred-1")
    http.delete.assert_called_once_with("/telephony_credentials/cred-1")
