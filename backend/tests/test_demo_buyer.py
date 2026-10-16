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
    "persona": {"name": "Marta", "gender": "female", "role": "Directora", "company": "Agencia Norte", "background": "8 reps. Usa Excel."},
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
    sent = json.loads(speech.calls[0].request.content)
    assert sent["response_format"] == "pcm"
    # Castilian accent goes as parameters, never inside the text (the model would read it aloud).
    assert sent["language"] == "es-ES" and "Castilian" in sent["instructions"] and sent["input"] == "¿Sí, dígame?"
    assert out["persona"]["name"] == "Marta"


@respx.mock
@pytest.mark.asyncio
async def test_build_scenario_passes_what_the_prospect_company_does(monkeypatch):
    chat = respx.post(demo_buyer.CHAT_URL).mock(return_value=_chat(json.dumps(SCENARIO)))
    respx.post(demo_buyer.SPEECH_URL).mock(return_value=httpx.Response(200, content=b"x"))

    await demo_buyer.build_scenario({"offer": "Copiloto", "niche": "agencias", "context": "Vende software de facturación a pymes"})

    assert "Vende software de facturación a pymes" in json.loads(chat.calls[0].request.content)["messages"][0]["content"]


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


@respx.mock
@pytest.mark.asyncio
async def test_voice_follows_the_persona_gender():
    man = {**SCENARIO, "persona": {**SCENARIO["persona"], "name": "Javier", "gender": "male"}}
    respx.post(demo_buyer.CHAT_URL).mock(return_value=_chat(json.dumps(man)))
    speech = respx.post(demo_buyer.SPEECH_URL).mock(return_value=httpx.Response(200, content=b"x"))

    out = await demo_buyer.build_scenario({"offer": "Copiloto de ventas", "niche": "agencias"})

    assert out["voice"] == demo_buyer.VOICES["male"]
    assert all(json.loads(c.request.content)["voice"] == "Orus" for c in speech.calls)


@respx.mock
@pytest.mark.asyncio
async def test_scenario_without_gender_is_rejected_instead_of_guessing_a_voice():
    broken = {**SCENARIO, "persona": {k: v for k, v in SCENARIO["persona"].items() if k != "gender"}}
    respx.post(demo_buyer.CHAT_URL).mock(return_value=_chat(json.dumps(broken)))
    with pytest.raises(demo_buyer.DemoBuyerError):
        await demo_buyer.build_scenario({"offer": "Copiloto de ventas", "niche": "agencias"})


HTML = """<html><head><title>Acme CRM</title><meta name="description" content="CRM para agencias">
<style>.x{}</style><script>var secret=1</script></head>
<body><h1>Vende más</h1><p>Software para equipos comerciales de agencias.</p>
<script>other()</script><footer>Contacto</footer></body></html>"""


def test_page_summary_keeps_visible_text_only():
    text = demo_buyer.page_summary_text(HTML)
    assert "Acme CRM" in text and "CRM para agencias" in text and "Vende más" in text
    assert "secret" not in text and "other()" not in text and ".x{}" not in text


@pytest.mark.parametrize(
    "url",
    ["http://localhost/admin", "http://127.0.0.1:8888/health", "http://10.0.0.5/", "http://169.254.169.254/latest", "ftp://example.com/x", "file:///etc/passwd"],
)
def test_private_and_non_http_urls_are_refused(url):
    with pytest.raises(demo_buyer.DemoBuyerError):
        demo_buyer._assert_public_url(url)


@respx.mock
@pytest.mark.asyncio
async def test_analyze_url_reads_the_page_and_returns_company_offer_industry(monkeypatch):
    monkeypatch.setattr(demo_buyer, "_assert_public_url", lambda url: None)
    respx.get("https://acme.example/").mock(
        return_value=httpx.Response(200, text=HTML, headers={"content-type": "text/html; charset=utf-8"})
    )
    chat = respx.post(demo_buyer.CHAT_URL).mock(
        return_value=_chat(json.dumps({"company": "Acme", "offer": "CRM para agencias.", "industry": "software comercial"}))
    )

    out = await demo_buyer.analyze_url("https://acme.example/")

    assert out == {"company": "Acme", "offer": "CRM para agencias.", "industry": "software comercial"}
    sent = json.loads(chat.calls[0].request.content)
    assert sent["model"] == "deepseek/deepseek-v4.1-flash" and "Vende más" in sent["messages"][0]["content"]


@respx.mock
@pytest.mark.asyncio
async def test_a_redirect_to_a_private_address_is_refused(monkeypatch):
    def resolve(host, port):
        ip = "93.184.216.34" if host == "acme.example" else host
        return [(2, 1, 6, "", (ip, port))]

    monkeypatch.setattr(demo_buyer.socket, "getaddrinfo", resolve)
    respx.get("https://acme.example/").mock(return_value=httpx.Response(302, headers={"location": "http://127.0.0.1:8888/health"}))
    private = respx.get("http://127.0.0.1:8888/health").mock(return_value=httpx.Response(200, text="secret"))
    with pytest.raises(demo_buyer.DemoBuyerError, match="pública"):
        await demo_buyer.analyze_url("https://acme.example/")
    assert not private.called
