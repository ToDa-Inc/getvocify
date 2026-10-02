from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.services.live_ticket import issue_ticket, user_for_ticket


def test_a_ticket_names_its_user_until_it_expires():
    ticket, expires = issue_ticket("user-1", now=1000)
    assert user_for_ticket(ticket, now=1001) == "user-1"
    assert user_for_ticket(ticket, now=expires + 1) is None


def test_a_forged_or_garbled_ticket_names_no_one():
    ticket, _ = issue_ticket("user-1", now=1000)
    payload, signature = ticket.rsplit(".", 1)
    forged, _ = issue_ticket("user-2", now=1000)
    assert user_for_ticket(f"{forged.rsplit('.', 1)[0]}.{signature}", now=1001) is None
    assert user_for_ticket("nonsense", now=1001) is None
    assert user_for_ticket("", now=1001) is None


def _live_client():
    from app.live_main import app

    return TestClient(app)


def test_the_live_service_serves_a_session_only_after_a_valid_ticket():
    served = AsyncMock()
    ticket, _ = issue_ticket("user-1")
    with patch("app.api.transcription.serve_live", served), _live_client() as client:
        with client.websocket_connect("/api/v1/transcription/live?user_id=someone-else&mode=copilot_channels") as ws:
            ws.send_json({"type": "Auth", "ticket": ticket})
    assert served.await_args.args[1] == "user-1"  # never the query's user


def test_without_a_ticket_the_live_service_closes():
    served = AsyncMock()
    with patch("app.api.transcription.serve_live", served), _live_client() as client:
        with client.websocket_connect("/api/v1/transcription/live?user_id=user-1") as ws:
            ws.send_json({"type": "Auth", "ticket": "forged.0000"})
            assert ws.receive_json()["type"] == "Error"
    served.assert_not_awaited()


def test_the_live_service_serves_nothing_but_live_audio():
    with _live_client() as client:
        assert client.get("/health").json()["service"] == "live"
        assert client.get("/api/v1/memos").status_code == 404
        assert client.post("/api/v1/transcription/ticket").status_code == 404
