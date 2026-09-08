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
