"""AI buyer for sales demos: a persona with pre-rendered objection clips plus free replies.

Text comes from an OpenRouter chat model and audio from an OpenRouter TTS model. The desktop plays the
audio on the Mac, so the island hears the buyer as the other side of the call (system audio).
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import ipaddress
import socket
import wave
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.config import settings
from app.services.llm.shared import extract_json

logger = logging.getLogger(__name__)

CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
SPEECH_URL = "https://openrouter.ai/api/v1/audio/speech"
CHAT_MODEL = "google/gemini-3.1-flash-lite"
TTS_MODEL = "google/gemini-3.8-flash-tts"
# Gemini TTS voices by the persona's gender: a man must not speak with a woman's voice.
VOICES = {"male": "Orus", "female": "Kore"}
ANALYZE_MODEL = "deepseek/deepseek-v4.1-flash"
FETCH_TIMEOUT = 15.0
FETCH_MAX_BYTES = 1_500_000
FETCH_MAX_REDIRECTS = 3
PAGE_TEXT_CHARS = 7000
MAX_OBJECTIONS = 6
REPLY_MAX_TOKENS = 90
HISTORY_TURNS = 12
PCM_RATE = 24000  # Gemini TTS only returns 24 kHz mono 16-bit PCM
TIMEOUT = 60.0

LANGUAGE_NAMES = {
    "es": "castellano de España (tuteo y vosotros, giros y vocabulario de España; nunca español latinoamericano)",
    "en": "English",
}
# Sent next to the text, not inside it: inside the text the model reads it aloud.
SPEECH_STYLE = {
    "es": {
        "instructions": "Speak with a natural Castilian Spanish accent from Spain, like a busy professional on a phone call.",
        "language": "es-ES",
    },
}


class DemoBuyerError(Exception):
    """Upstream (OpenRouter) failed or returned something unusable."""


def _headers() -> dict[str, str]:
    key = settings.OPENROUTER_API_KEY
    if not key:
        raise DemoBuyerError("OPENROUTER_API_KEY is not configured")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


async def _chat(client: httpx.AsyncClient, messages: list[dict], *, max_tokens: int, json_mode: bool = False) -> str:
    body: dict[str, Any] = {
        "model": CHAT_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "reasoning": {"effort": "none"},
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    resp = await client.post(CHAT_URL, headers=_headers(), json=body)
    if resp.status_code != 200:
        raise DemoBuyerError(f"chat {resp.status_code}: {resp.text[:200]}")
    try:
        return (resp.json()["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, ValueError) as exc:
        raise DemoBuyerError("chat returned no content") from exc


def pcm_to_wav(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(PCM_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


async def _speak(client: httpx.AsyncClient, text: str, voice: str, language: str = "es") -> str:
    resp = await client.post(
        SPEECH_URL,
        headers=_headers(),
        json={"model": TTS_MODEL, "input": text, "voice": voice, "response_format": "pcm", **SPEECH_STYLE.get(language, {})},
    )
    if resp.status_code != 200 or not resp.content:
        raise DemoBuyerError(f"tts {resp.status_code}: {resp.text[:200]}")
    return base64.b64encode(pcm_to_wav(resp.content)).decode("ascii")


def persona_system_prompt(persona: dict, language: str) -> str:
    lang = LANGUAGE_NAMES.get(language, LANGUAGE_NAMES["es"])
    return (
        f"You are {persona['name']} ({persona.get('gender', 'female')}), {persona['role']} at {persona['company']}. {persona['background']} "
        f"You are the BUYER on a sales call and the other person is the seller. Speak {lang}, natural phone "
        "register, at most two short sentences per turn, no lists, no stage directions. Stay skeptical and "
        "time-poor. If the seller has not resolved your last concern, press on it; if they did, move to the "
        "next concern. Never say you are an AI."
    )


async def build_scenario(brief: dict) -> dict:
    """Persona, opening line and objection deck for one prospect, with every line already spoken."""
    language = brief.get("language") or "es"
    lang = LANGUAGE_NAMES.get(language, LANGUAGE_NAMES["es"])
    prompt = (
        "Design a realistic BUYER for a sales-demo roleplay. Return JSON only with keys: "
        "persona {name (a common first name and surname for the language and country), gender (male or female, "
        "matching the name), role, company, background (2 sentences, includes team size and current tools)}, "
        "opening (the buyer's first line when picking up the phone, one short sentence), "
        f"objections (a list of {MAX_OBJECTIONS} items {{label (2-3 words, e.g. Precio), line (what the buyer "
        "says, 1-2 short sentences, specific to this industry)}}). Cover price, needing a partner or boss, an "
        "existing tool, no time, send-me-info, and trust/risk. "
        f"All spoken text in {lang}.\n"
        f"Seller offer: {brief['offer']}\nBuyer industry: {brief['niche']}\n"
        f"Buyer company: {brief.get('company') or 'invent one'}\nBuyer name: {brief.get('prospect_name') or 'invent one'}"
    )
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        raw = await _chat(client, [{"role": "user", "content": prompt}], max_tokens=900, json_mode=True)
        try:
            data = extract_json(raw)
            persona = data["persona"]
            for field in ("name", "role", "company", "background"):
                persona[field] = str(persona[field])
            persona["gender"] = str(persona["gender"]).lower()
            if persona["gender"] not in VOICES:
                raise ValueError("gender")
            opening = str(data["opening"])
            objections = [
                {"label": str(o["label"]), "line": str(o["line"])} for o in data["objections"][:MAX_OBJECTIONS]
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise DemoBuyerError("scenario JSON was not usable") from exc
        voice = brief.get("voice") or VOICES[persona["gender"]]
        lines = [opening, *[o["line"] for o in objections]]
        audios = await asyncio.gather(*[_speak(client, line, voice, language) for line in lines])
    return {
        "persona": persona,
        "voice": voice,
        "language": language,
        "opening": {"id": "opening", "label": "Apertura", "line": opening, "audio_b64": audios[0]},
        "objections": [
            {"id": f"obj-{i + 1}", **o, "audio_b64": audios[i + 1]} for i, o in enumerate(objections)
        ],
        "mime": "audio/wav",
    }


async def buyer_reply(persona: dict, language: str, voice: str, history: list[dict], seller_text: str) -> dict:
    """One free-form buyer turn answering what the seller just said."""
    messages: list[dict] = [{"role": "system", "content": persona_system_prompt(persona, language)}]
    for turn in history[-HISTORY_TURNS:]:
        messages.append({"role": "assistant" if turn["role"] == "buyer" else "user", "content": turn["text"]})
    messages.append({"role": "user", "content": seller_text})
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        line = await _chat(client, messages, max_tokens=REPLY_MAX_TOKENS)
        if not line:
            raise DemoBuyerError("empty buyer reply")
        audio = await _speak(client, line, voice, language)
    return {"line": line, "audio_b64": audio, "mime": "audio/wav"}


# ── Reading a company's website ─────────────────────────────────────────────────


class _PageText(HTMLParser):
    """Title, meta description and visible text of a page, without scripts and styles."""

    SKIP = {"script", "style", "noscript", "svg", "template", "head"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self.parts: list[str] = []
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            a = dict(attrs)
            name = (a.get("name") or a.get("property") or "").lower()
            if name in ("description", "og:description") and not self.description:
                self.description = (a.get("content") or "").strip()
        elif tag in self.SKIP:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag in self.SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        text = " ".join(data.split())
        if not text:
            return
        if self._in_title:
            self.title += text
        elif not self._skip:
            self.parts.append(text)


def _assert_public_url(url: str) -> None:
    """Refuses anything that is not a public http(s) address: this server must not fetch its own network."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise DemoBuyerError("La web tiene que empezar por http:// o https://")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise DemoBuyerError("No encuentro esa web") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise DemoBuyerError("Esa dirección no es una web pública")


async def _fetch_page(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; VocifyBot/1.0)", "Accept": "text/html,*/*;q=0.5"}
    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT, follow_redirects=False, headers=headers) as client:
        for _ in range(FETCH_MAX_REDIRECTS + 1):
            await asyncio.to_thread(_assert_public_url, url)
            async with client.stream("GET", url) as resp:
                if resp.is_redirect and resp.headers.get("location"):
                    url = urljoin(url, resp.headers["location"])
                    continue
                if resp.status_code != 200:
                    raise DemoBuyerError(f"La web respondió {resp.status_code}")
                if "html" not in resp.headers.get("content-type", "html"):
                    raise DemoBuyerError("Esa dirección no es una página web")
                body = b""
                async for chunk in resp.aiter_bytes():
                    body += chunk
                    if len(body) >= FETCH_MAX_BYTES:
                        break
                return body.decode(resp.encoding or "utf-8", errors="replace")
    raise DemoBuyerError("Demasiadas redirecciones")


def page_summary_text(html: str) -> str:
    parser = _PageText()
    parser.feed(html)
    head = " | ".join(x for x in (parser.title, parser.description) if x)
    return f"{head}\n{' '.join(parser.parts)}"[:PAGE_TEXT_CHARS]


async def analyze_url(url: str) -> dict:
    """What a company's website says it sells, who it serves and what it is called."""
    text = page_summary_text(await _fetch_page(url.strip()))
    if len(text.strip()) < 40:
        raise DemoBuyerError("No he podido leer texto en esa web")
    prompt = (
        "From this website text, return JSON only with keys: company (the brand name), offer (what they sell and "
        "to whom, in 1-2 plain sentences, in the language of the site), industry (the segment they work in or "
        "serve, 3-8 words, in the language of the site). Use only what the text says; if a key is not stated, "
        "use an empty string.\n\nWebsite text:\n" + text
    )
    body = {
        "model": ANALYZE_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 300,
        "response_format": {"type": "json_object"},
        "reasoning": {"effort": "none"},
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(CHAT_URL, headers=_headers(), json=body)
    if resp.status_code != 200:
        raise DemoBuyerError(f"analyze {resp.status_code}: {resp.text[:200]}")
    try:
        data = extract_json(resp.json()["choices"][0]["message"]["content"] or "")
        return {k: str(data.get(k) or "").strip() for k in ("company", "offer", "industry")}
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise DemoBuyerError("No he entendido esa web") from exc
