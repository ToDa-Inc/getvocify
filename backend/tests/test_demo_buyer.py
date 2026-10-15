import base64
import json

import httpx
import pytest
import respx

from app.config import settings
from app.services import demo_buyer


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "test-key")


def _chat(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


SCENARIO = {
    "persona": {"name": "Marta", "role": "Directora", "company": "Agencia Norte", "background": "8 reps. Usa Excel."},
    "opening": "¿Sí, dígame?",
    "objections": [
        {"label": "Precio", "line": "Es caro para nosotros."},
        {"label": "Socio", "line": "Lo hablo con mi socio."},
    ],
}


@respx.mock
@pytest.mark.asyncio
async def test_build_scenario_speaks_opening_and_every_objection():
    respx.post(demo_buyer.CHAT_URL).mock(return_value=_chat(json.dumps(SCENARIO)))
    speech = respx.post(demo_buyer.SPEECH_URL).mock(return_value=httpx.Response(200, content=b"mp3-bytes"))

    out = await demo_buyer.build_scenario({"offer": "Copiloto de ventas", "niche": "agencias"})

    assert speech.call_count == 3
    assert [o["label"] for o in out["objections"]] == ["Precio", "Socio"]
    wav = base64.b64decode(out["opening"]["audio_b64"])
    assert wav[:4] == b"RIFF" and wav.endswith(b"mp3-bytes")
    assert json.loads(speech.calls[0].request.content)["response_format"] == "pcm"
    assert out["persona"]["name"] == "Marta"


@respx.mock
@pytest.mark.asyncio
async def test_build_scenario_rejects_unusable_json():
    respx.post(demo_buyer.CHAT_URL).mock(return_value=_chat('{"persona": {}}'))
    with pytest.raises(demo_buyer.DemoBuyerError):
        await demo_buyer.build_scenario({"offer": "x y z", "niche": "agencias"})


@respx.mock
@pytest.mark.asyncio
async def test_buyer_reply_sends_history_and_returns_audio():
    chat = respx.post(demo_buyer.CHAT_URL).mock(return_value=_chat("¿Y cuánto cuesta?"))
    respx.post(demo_buyer.SPEECH_URL).mock(return_value=httpx.Response(200, content=b"audio"))

    out = await demo_buyer.buyer_reply(
        SCENARIO["persona"],
        "es",
        "Kore",
        [{"role": "buyer", "text": "¿Sí?"}, {"role": "seller", "text": "Hola"}],
        "Ayudamos con objeciones",
    )

    sent = json.loads(chat.calls[0].request.content)["messages"]
    assert [m["role"] for m in sent] == ["system", "assistant", "user", "user"]
    assert out["line"] == "¿Y cuánto cuesta?"
    assert out["audio_b64"]


@respx.mock
@pytest.mark.asyncio
async def test_tts_failure_surfaces_as_demo_buyer_error():
    respx.post(demo_buyer.CHAT_URL).mock(return_value=_chat("Hola"))
    respx.post(demo_buyer.SPEECH_URL).mock(return_value=httpx.Response(502, text="upstream"))
    with pytest.raises(demo_buyer.DemoBuyerError):
        await demo_buyer.buyer_reply(SCENARIO["persona"], "es", "Kore", [], "Hola")


def test_demo_buyer_route_is_404_unless_the_company_flag_is_on(monkeypatch):
    from fastapi import HTTPException

    from app.api import demo
    from app.services.company import Membership

    member = Membership(id="m1", company_id="c1", user_id="u1", role="owner", status="active")
    monkeypatch.setattr(demo, "is_enabled", lambda _sb, _cid, flag: False)
    with pytest.raises(HTTPException) as err:
        demo.require_demo_buyer(member, object())
    assert err.value.status_code == 404

    monkeypatch.setattr(demo, "is_enabled", lambda _sb, cid, flag: (cid, flag) == ("c1", "DEMO_BUYER_ENABLED"))
    assert demo.require_demo_buyer(member, object()) is member
