"""Buenas prácticas: situations written by Vocify that a company imports into a call type's «Cómo decide Vocify».

They are playbook content, not brain: the live brain only ever reads the situations a company has in its playbook, its own
or imported, the same way. A practice says when it applies, what to do and what not to do, with no line to recite (lines
were copied where they did not fit). An imported situation keeps the id of its practice (`practice`), so the page can show
which ones the company already has; editing it makes it the company's own.

The first pack is for calls whose goal is to book a meeting, written from Vocify's own cold calls (the criterion its
founder wrote and what replaying those calls showed). Other goals have none yet.
"""

from __future__ import annotations

from typing import Optional

from app.services.playbooks.motion import goal_for

MEETING_BOOKED = [
    {
        "id": "no_sabe_quien_llama",
        "name": "No sabe quién llama",
        "when": "Dice que no te ubica o pregunta de qué va la llamada («no te ubico», «no caigo», «¿de qué?»).",
        "do": "Presentarse en una frase y decir por qué le llamas a él en concreto. No saber quién llama no es falta de tiempo.",
        "avoid": "Soltar todo el discurso de golpe. Preguntar si es mal momento solo porque no te ubica.",
    },
    {
        "id": "ya_lo_tiene_resuelto",
        "name": "Dice que ya lo tiene resuelto",
        "when": "Afirma que lo tiene resuelto o automatizado («ya lo tenemos», «lo tenemos controlado»).",
        "do": "Entender qué significa «resuelto» para él (una herramienta, un proceso interno, resultados) y cómo funciona en la "
              "práctica, antes de comparar nada. Si responde en general, una pregunta abierta sobre cómo pasa en el día a día.",
        "avoid": "Rebatirlo o tratarlo como una objeción. Preguntar lo que ya ha contado. Tomar una respuesta genérica como una "
                 "explicación completa, o como falsa.",
    },
    {
        "id": "ya_usa_algo_parecido",
        "name": "Ya usa algo parecido",
        "when": "Ya usa una herramienta, una consultora o un método propio para lo mismo.",
        "do": "Entender qué hace y qué le ha dado desde que lo usa. Presentar lo vuestro solo cuando aparezca una necesidad "
              "concreta que eso no cubre.",
        "avoid": "Demostrar diferencias funcionales. Preguntar por límites de su solución que no ha contado. Dar por hecho que "
                 "tiene un problema.",
    },
    {
        "id": "le_quita_importancia",
        "name": "Le quita importancia",
        "when": "Reconoce algo pero le resta peso («no lo veo crítico», «no lo veo tanto», «pasa, pero no nos afecta»).",
        "do": "Si sigue hablando y no sabes por qué no le importa, entender el motivo: lo resuelven de otra forma, les cuesta "
              "poco o tienen otras prioridades. Con eso decides si seguir o cambiar de tema.",
        "avoid": "Volver a demostrarle que el problema existe: ya lo ha reconocido. Abandonar al primer «no es crítico».",
    },
    {
        "id": "aparece_una_necesidad",
        "name": "Aparece una posible necesidad",
        "when": "Menciona una dificultad, algo mejorable o un resultado que no consigue.",
        "do": "Preguntar lo que más aclare según lo que falte: qué pasa, qué consecuencia tiene, cómo lo resuelven hoy o si "
              "quieren mejorarlo. Una sola pregunta, a partir de lo que acaba de decir.",
        "avoid": "Presentar el producto enseguida. Presuponer pérdidas o fallos que no ha mencionado. Seguir una lista de "
                 "preguntas.",
    },
    {
        "id": "todo_funciona_bien",
        "name": "Dice que todo funciona bien",
        "when": "Afirma que está contento con cómo trabajan y no busca alternativas.",
        "do": "Tomarlo en serio. Si sigue receptivo y queda una duda importante, entender cómo mide sus resultados. Si no, "
              "descartar bien también es un buen resultado.",
        "avoid": "Fabricar una necesidad.",
    },
    {
        "id": "dice_que_ahora_no",
        "name": "Dice que ahora no",
        "when": "«Ahora no», «no me interesa», «estoy liado», «llámame más adelante».",
        "do": "Distinguir tres casos. Sin interés y con un motivo (ya han comprado otra cosa, no lo necesitan): no proponer "
              "reunión, como mucho quedarse con el contacto que ofrezca. Una objeción: entenderla. Falta de tiempo con interés "
              "(un evento, una baja, mucho trabajo): acordar cuándo retomarlo, con la fecha que él diga.",
        "avoid": "Proponer una demo tras un no con motivo. Proponer una fecha antes que la que ha dado.",
    },
    {
        "id": "pide_informacion",
        "name": "Pide que le mandes información",
        "when": "«Mándame un correo», «mándame info», «escríbeme por LinkedIn».",
        "do": "Confirmar que se lo mandas por el canal que ha dicho. Si ya ha dicho cuándo hablar, confirmarlo tal cual. Si no hay "
              "nada fijado y hay interés, proponer verlo juntos cuando lo haya leído.",
        "avoid": "Proponer días que contradigan lo que ha dicho. Insistir en la reunión si ha dejado claro que antes quiere leerlo.",
    },
    {
        "id": "de_donde_tienes_mi_contacto",
        "name": "Pregunta de dónde tienes su contacto",
        "when": "«¿De dónde has sacado mi teléfono?», «¿cómo tienes mi correo?».",
        "do": "Contestarlo primero, con la fuente real que tenga la empresa (una respuesta aprobada del playbook). Si no la hay, "
              "que lo conteste el comercial.",
        "avoid": "Inventar la fuente. Seguir con la llamada sin contestarle.",
    },
    {
        "id": "te_deriva",
        "name": "Te deriva a otra persona",
        "when": "Ya no lleva el tema, está de baja o dice que lo decide otra persona.",
        "do": "Agradecerlo y conseguir lo necesario para llegar a esa persona: nombre, canal y si puedes decir que hablaste con él.",
        "avoid": "Preguntar lo que ya ha dicho (si ya te dio permiso para nombrarle, no lo vuelvas a pedir). Seguir vendiéndole a él.",
    },
]

BY_GOAL = {"meeting_booked": MEETING_BOOKED}


def practices_for(sales_motion_key: str, goal: Optional[str] = None) -> list[dict]:
    """The practices for a call type: by its goal (the catalog's when `goal` is not given); none when there is no pack."""
    return [dict(p) for p in BY_GOAL.get(goal or goal_for(sales_motion_key) or "", [])]
