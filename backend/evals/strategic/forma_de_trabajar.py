"""The experiment of 2026-10-27: does a playbook that says what a good outcome is, and how this company conducts these
calls, make better cards than the goal fixed in code? Written by hand for Vocify's cold calls, as a customer would write it
in the playbook (no interface yet). Neither block is a SOURCE: a card can never rest on them to state a fact.

- "base": turns-6b as it runs in the pilot (the goal fixed in code for the call type).
- "goal": the company's goal instead, with the other good outcomes and when to stop pursuing it.
- "criteria": that goal plus the seven criteria of «Cómo trabajamos».
- "momentos": that goal plus what to do in each moment of the call (with_moments): the reading names the moment first.
"""

from __future__ import annotations

import re

VARIANTS = ("base", "goal", "criteria", "momentos")

GOAL = """COMPANY GOAL FOR THIS TYPE OF CALL (written by the company; the direction, not an order):
- Objetivo principal: agendar una reunión (demo) con alguien que tenga una necesidad real, con día y hora acordados.
- También son buenos resultados: encontrar a la persona que decide; acordar un seguimiento ligado a algo concreto (un cambio en el equipo, una fecha); descalificar cuando no hay encaje.
- Dejar de perseguir la reunión cuando: no existe necesidad después de explorarla razonablemente, hay un rechazo claro o no hay encaje."""

CRITERIA = """HOW THIS COMPANY CONDUCTS THESE CALLS («Cómo trabajamos»; guidance on how to decide, never a source of facts):
1. No asumir dolor. Si el prospect no reconoce la necesidad, no insistir en ella.
2. Profundizar antes de presentar. Cuando mencione un problema, entender qué ocurre y qué consecuencias tiene.
3. Seguir las señales nuevas. Si aparece un cambio relevante en su negocio, explorar si genera una necesidad, sin darla por hecha.
4. No vender funcionalidades por acumulación. Si ya tiene resuelto un problema, no ofrecerle más funciones relacionadas.
5. Respetar la autonomía del comprador. No convertir las preferencias de su equipo en errores que haya que corregir.
6. Reconocer cuándo avanzar. Si hay necesidad e interés, proponer un siguiente paso en lugar de seguir preguntando.
7. Saber terminar. Cuando no hay encaje y se ha explorado razonablemente, cerrar sin forzar la conversación."""

_GOAL_LINE = re.compile(r"^USUAL GOAL FOR THIS TYPE OF CALL[^\n]*$", re.M)


def with_variant(context: str, variant: str) -> str:
    """The reading's context with the goal fixed in code replaced by the company's own (and its criteria)."""
    if variant == "base":
        return context
    if not _GOAL_LINE.search(context):
        raise ValueError("the context has no goal line to replace")
    block = GOAL if variant == "goal" else f"{GOAL}\n\n{CRITERIA}"
    return _GOAL_LINE.sub(lambda _: block, context, count=1)


def moments_block(moments: list[dict]) -> str:
    """What the company does in each moment ({id, name, line}); the reading names the moment ("moment") before deciding."""
    lines = "\n".join(f"- {m['id']} · {m['name']}: {m['line']}" for m in moments if m["line"].strip())
    return ("HOW THIS COMPANY ACTS IN EACH MOMENT OF THE CALL (written by the company; guidance on how to decide, never a "
            "source of facts):\n"
            "First recognise the moment the call is in now (\"moment\": its id, or \"none\" when none fits), from what "
            "they have said so far, not only their last words. Then act as the company says for that moment: it comes "
            "before the goal.\n" + lines)


def style_block(style: list[str]) -> str:
    """How every card is worded, whatever the moment (one line per setting the company changed)."""
    return ("HOW THIS COMPANY WANTS EVERY CARD WORDED (applies to every card; it changes how the card is said, never what "
            "to do):\n" + "\n".join(f"- {line}" for line in style))


def with_moments(context: str, moments: list[dict], style: list[str] | None = None) -> str:
    """The reading's context with the company's goal, what to do in each moment and how cards are worded, instead of
    the goal fixed in code."""
    if not _GOAL_LINE.search(context):
        raise ValueError("the context has no goal line to replace")
    block = f"{GOAL}\n\n{moments_block(moments)}" + (f"\n\n{style_block(style)}" if style else "")
    return _GOAL_LINE.sub(lambda _: block, context, count=1)
