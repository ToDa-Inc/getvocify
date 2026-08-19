"""Live flash-lite language pick. Skips if OPENROUTER_API_KEY is unset."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
load_dotenv(Path(__file__).parent / ".env")

CATALAN_AS_SPANISH = """
SPEAKER: S2
Miquel. Buenas.

SPEAKER: S1
Buenas, ¿qué tal? Que te están, que craban trucadas, adelante.
Dani, fundador de Vocify. No sé si me ubicas.

SPEAKER: S2
Pues no, no, no.

SPEAKER: S1
Si antes que ya tens un CRM propio, entonces que esta afecta más segura para
para el que vosaltres de su bebé. Yo el que facilito me es arrest es la página
de estos comerciales. Traíamos un 1 alta porcentaje. Has da pendra decisions
per sensations, més que han data. No sé si eso pasa.

SPEAKER: S2
Sí. Yo al que tú ya iría es pásame información por email.

SPEAKER: S1
els correos yo me tengo muy buena rebuta. No sé si tens en aquesta semana
o la que veo cuando, no sé si estás a vacantes tampoco, tens 15 minutos.

SPEAKER: S2
Ahora lo hago. En las vacances, vale. Y la quincena es dolenta.
"""

PURE_SPANISH = """
S1: Hola Miguel, buenos días, te llamo de Vocify. Soy Dani, el fundador.
S2: Hola, dime.
S1: Llamo porque veo que sois directores de ventas y quería enseñaros el producto.
S2: Ahora no tengo tiempo. Envíame un correo y lo vemos en septiembre.
S1: Perfecto, te lo mando hoy. Gracias.
"""

PURE_ENGLISH = """
S1: Hey Mike, this is Dani from Vocify. Quick call about the CRM follow-up.
S2: Sure, what's up?
S1: We help sales reps log calls automatically. Fifteen minutes next week?
S2: Email me and I'll take a look.
"""


async def main() -> int:
    if not os.getenv("OPENROUTER_API_KEY"):
        print("SKIP: OPENROUTER_API_KEY not set")
        return 0

    from app.services.stt_batch import detect_stt_language

    cases = [
        ("catalan-as-spanish", CATALAN_AS_SPANISH, ["ca", "es"], "ca"),
        ("pure-spanish", PURE_SPANISH, ["ca", "es"], "es"),
        ("english", PURE_ENGLISH, ["en", "es"], "en"),
        ("spanish-only-settings", PURE_SPANISH, ["es"], "es"),
    ]
    failed = 0
    for name, text, allowed, expected in cases:
        picked = await detect_stt_language(text, allowed)
        ok = picked == expected
        failed += int(not ok)
        print(f"{'OK' if ok else 'FAIL'} {name}: allowed={allowed} picked={picked} expected={expected}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
