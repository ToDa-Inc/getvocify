"""AI buyer for sales demos: a persona with pre-rendered objection clips plus free replies.

Text comes from an OpenRouter chat model and audio from an OpenRouter TTS model. The desktop plays the
audio on the Mac, so the island hears the buyer as the other side of the call (system audio).
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import wave
from typing import Any

import httpx

from app.config import settings
from app.services.llm.shared import extract_json

logger = logging.getLogger(__name__)

CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
SPEECH_URL = "https://openrouter.ai/api/v1/audio/speech"
CHAT_MODEL = "google/gemini-3.1-flash-lite"
TTS_MODEL = "google/gemini-3.8-flash-tts"
DEFAULT_VOICE = "Kore"
MAX_OBJECTIONS = 6
REPLY_MAX_TOKENS = 90
HISTORY_TURNS = 12
PCM_RATE = 24000  # Gemini TTS only returns 24 kHz mono 16-bit PCM
TIMEOUT = 60.0

LANGUAGE_NAMES = {"es": "español de España", "en": "English"}


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


async def _speak(client: httpx.AsyncClient, text: str, voice: str) -> str:
    resp = await client.post(
        SPEECH_URL,
        headers=_headers(),
        json={"model": TTS_MODEL, "input": text, "voice": voice, "response_format": "pcm"},
    )
    if resp.status_code != 200 or not resp.content:
        raise DemoBuyerError(f"tts {resp.status_code}: {resp.text[:200]}")
    return base64.b64encode(pcm_to_wav(resp.content)).decode("ascii")


def persona_system_prompt(persona: dict, language: str) -> str:
    lang = LANGUAGE_NAMES.get(language, LANGUAGE_NAMES["es"])
    return (
        f"You are {persona['name']}, {persona['role']} at {persona['company']}. {persona['background']} "
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
        "persona {name, role, company, background (2 sentences, includes team size and current tools)}, "
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
            opening = str(data["opening"])
            objections = [
                {"label": str(o["label"]), "line": str(o["line"])} for o in data["objections"][:MAX_OBJECTIONS]
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise DemoBuyerError("scenario JSON was not usable") from exc
        voice = brief.get("voice") or DEFAULT_VOICE
        lines = [opening, *[o["line"] for o in objections]]
        audios = await asyncio.gather(*[_speak(client, line, voice) for line in lines])
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
        audio = await _speak(client, line, voice)
    return {"line": line, "audio_b64": audio, "mime": "audio/wav"}
