from unittest.mock import MagicMock, patch

from app.services.telephony.telnyx_client import TelnyxClient


def test_dial_posts_from_chosen_by_server():
    http = MagicMock()
    http.post.return_value.status_code = 200
    http.post.return_value.json.return_value = {
        "data": {"call_control_id": "v3:pstn"}
    }
    http.post.return_value.raise_for_status = lambda: None
    client = TelnyxClient(api_key="KEY", connection_id="CONN", http=http)
    result = client.dial(
        to="+34600111222",
        caller_id="+34600999888",
        link_to="v3:parked",
    )
    assert result["call_control_id"] == "v3:pstn"
    body = http.post.call_args.kwargs["json"]
    assert body["from"] == "+34600999888"
    assert body["to"] == "+34600111222"
    assert body["connection_id"] == "CONN"
    assert "bridge_intent" not in body
    assert body["link_to"] == "v3:parked"


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


def test_delete_telephony_credential_uses_rest_path():
    http = MagicMock()
    http.delete.return_value.status_code = 200
    http.delete.return_value.content = b""
    http.delete.return_value.raise_for_status = lambda: None
    client = TelnyxClient(api_key="KEY", connection_id="CONN", http=http)
    client.delete_telephony_credential("cred-1")
    http.delete.assert_called_once_with("/telephony_credentials/cred-1")
