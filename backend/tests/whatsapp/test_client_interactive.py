import json

import httpx
import respx

from app.services.whatsapp.client import WhatsAppClient


@respx.mock
async def test_send_interactive_list_payload():
    client = WhatsAppClient()
    client.access_token = "t"
    client.phone_number_id = "pn"
    route = respx.post("https://graph.facebook.com/v21.0/pn/messages").mock(
        return_value=httpx.Response(200, json={"messages": [{"id": "wamid.x"}]})
    )
    await client.send_interactive_list(
        "+34600",
        "Elige deal",
        "Cambiar",
        [{"title": "Deal", "rows": [{"id": "pick:skip_deal", "title": "Sin deal"}]}],
    )
    payload = json.loads(route.calls[0].request.content)
    assert payload["type"] == "interactive"
    assert payload["interactive"]["type"] == "list"
    assert payload["interactive"]["action"]["button"] == "Cambiar"
    assert payload["interactive"]["action"]["sections"][0]["rows"][0]["id"] == "pick:skip_deal"
