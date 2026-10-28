"""An unhandled exception still answers with CORS headers, so the browser reads the 500 instead of
reporting "Failed to fetch" (the dashboard's Transcribe on 2026-10-28)."""

from fastapi.testclient import TestClient

from app.main import app


async def _boom():
    raise RuntimeError("duplicate key value violates unique constraint")


app.add_api_route("/__test__/boom", _boom, methods=["POST"])


def test_an_unhandled_500_carries_cors_and_the_request_id():
    client = TestClient(app, raise_server_exceptions=False)
    res = client.post("/__test__/boom", headers={"Origin": "https://app.getvocify.com"})
    assert res.status_code == 500
    assert res.headers.get("access-control-allow-origin") == "https://app.getvocify.com"
    assert res.json()["detail"] == "Internal server error"
    assert res.json()["request_id"]
