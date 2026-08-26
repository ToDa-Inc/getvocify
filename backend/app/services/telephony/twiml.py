"""TwiML for Vocify outbound calls.

Pure string generation — no network, no DB, no settings reads. The webhook
resolves identity and caller ID, then asks this module for the XML.

Two documents are produced:

  * the outbound document, returned to the TwiML App's Voice URL, which dials
    the prospect from the SDR's verified number and records dual-channel;
  * the whisper document, returned via the ``<Number url>`` attribute, which
    plays the recording disclosure to the *prospect only* after they answer
    and before the legs are bridged.

`record-from-answer-dual` is a hard requirement, not a preference: HubSpot's
transcription pipeline splits the file by channel and expects the caller on
channel 1 and the recipient on channel 2.
"""

from __future__ import annotations

import re

from twilio.twiml.voice_response import Dial, VoiceResponse

E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
_SEPARATORS_RE = re.compile(r"[\s().\-/]")
# Remaining digits after stripping an embedded country code must reach this
# length to treat the input as ambiguous (country code + national, no +/00).
_MIN_AMBIGUOUS_NATIONAL_DIGITS = 8

DEFAULT_RECORDING_ANNOUNCEMENT_ES = (
    "Le informamos de que esta llamada se graba y se transcribe para "
    "registrarla en nuestro sistema de gestión comercial. "
    "Si no desea que se grabe, indíquelo y la detendremos."
)


class InvalidPhoneNumber(ValueError):
    """Raised when a number cannot be expressed in E.164."""


def normalize_e164(raw: str, default_country_code: str = "34") -> str:
    """Best-effort E.164 for numbers coming from CRM free-text fields."""
    value = _SEPARATORS_RE.sub("", (raw or "").strip())
    if not value:
        raise InvalidPhoneNumber("phone number is empty")

    if value.startswith("00"):
        value = "+" + value[2:]
    elif not value.startswith("+"):
        national = value.lstrip("0")
        if (
            national.isdigit()
            and national.startswith(default_country_code)
            and len(national) - len(default_country_code) >= _MIN_AMBIGUOUS_NATIONAL_DIGITS
        ):
            raise InvalidPhoneNumber(
                f"ambiguous number {raw!r}: starts with country code "
                f"{default_country_code} without + or 00 prefix"
            )
        # A leading 0 is a national trunk prefix in most of the EU.
        value = f"+{default_country_code}{national}"

    if not E164_RE.match(value):
        raise InvalidPhoneNumber(f"cannot normalize {raw!r} to E.164 (got {value!r})")
    return value


def _require_e164(label: str, value: str) -> str:
    if not E164_RE.match(value or ""):
        raise InvalidPhoneNumber(f"{label} must already be E.164, got {value!r}")
    return value


def build_outbound_twiml(
    *,
    to: str,
    caller_id: str,
    recording_callback_url: str,
    whisper_url: str,
    timeout: int = 30,
) -> str:
    """Dial `to` from `caller_id`, recording both legs on separate channels."""
    _require_e164("to", to)
    _require_e164("caller_id", caller_id)

    response = VoiceResponse()
    dial = Dial(
        caller_id=caller_id,
        record="record-from-answer-dual",
        recording_status_callback=recording_callback_url,
        recording_status_callback_event="completed",
        # Keeps the SDR hearing ringback while the disclosure plays.
        answer_on_bridge=True,
        timeout=timeout,
    )
    dial.number(to, url=whisper_url)
    response.append(dial)
    return str(response)


def build_whisper_twiml(*, announcement: str, language: str = "es-ES") -> str:
    """Disclosure played to the called party before the legs are bridged.

    Twilio forbids `<Dial>` inside a `<Number url>` document.
    """
    response = VoiceResponse()
    response.say(announcement, language=language)
    return str(response)
