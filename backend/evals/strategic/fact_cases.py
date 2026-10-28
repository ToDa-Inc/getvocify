"""The fact check on the lines that slipped or were wrongly blocked, and on every line a judge found well written.

    cd backend && .venv/bin/python -m evals.strategic.fact_cases --runs RUN.json,RUN.json --verdicts V.json,V.json

Each case runs the real fact check (DeepSeek on Together, about 0.3 s and a fraction of a cent) with what the replay
gives it: the card's whole approved source and the conversation up to the moment it appeared.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.strategic.run import CALLS, ends  # noqa: E402

# (call, second, act, source, line, expected): lines from the 22 October replays of three unused calls.
CASES = [
    # Slipped through in 3.1 (moves were not checked, or the check let a promise pass).
    ("916d1bd8-real", 369, "move", "context", "No, no te miento: lo que ves es AnyDesk y el retardo del fin de turno.", "block"),
    ("916d1bd8-real", 368, "move", "context", "Claro, te doy acceso para que lo pruebes tú mismo. ¿Te lo mando al mail?", "block"),
    # The approved answer says it («en la propuesta se deja por escrito qué funciona desde el primer día»): the judge that
    # called it invented had only the discovery playbook's entries, not the company-wide ones the brain reads.
    ("916d1bd8-real", 303, "answer", "objection:custom:se_integra_con_nuestro_crm",
     "¿Qué CRM propio es y qué campos tendríais que actualizar? Con Dani revisamos la API y os digo qué funciona desde el día uno.", "pass"),
    # A guarantee the approved answer does not give.
    ("916d1bd8-real", 303, "answer", "objection:custom:se_integra_con_nuestro_crm",
     "Con vuestro CRM propio funciona todo desde el primer día, sin desarrollo.", "block"),
    ("916d1bd8-real", 465, "move", "context", "Perfecto, quedamos el martes a las 10 y te mando la invitación.", "block"),
    ("ea5cb466-real", 161, "move", "context", "Granola no te ayuda durante la reunión, solo después.", "block"),
    # Invented on purpose (kept blocked since 3.1).
    ("916d1bd8-real", 300, "answer", "offer", "Sí, nos integramos directamente con MP y lo dejamos funcionando en un día.", "block"),
    ("916d1bd8-real", 60, "answer", "offer", "Gonzalo y yo fundamos Vocify hace cinco años.", "block"),
    ("916d1bd8-real", 180, "answer", "objection:price", "Cuesta 49 euros por comercial al mes, sin permanencia.", "block"),
    ("1778148f-real", 120, "answer", "offer", "Sí, la llamada se está grabando y te paso el resumen.", "block"),
    # Fact, proposal or the seller's own action (22 October, Dani): a fact or guarantee needs the source; a proposal is
    # fine; an action the seller controls is fine, but what it adds (a person, an agreed date) needs the conversation.
    ("0c439183", 300, "move", "context", "La integración estará funcionando desde mañana.", "block"),
    ("0c439183", 449, "move", "context", "¿Te parece si lo retomamos en enero?", "pass"),
    ("0c439183", 200, "move", "context", "Quedamos en enero entonces.", "block"),
    ("0c439183", 143, "move", "context", "Te mando la información hoy.", "pass"),
    ("0c439183", 143, "move", "context", "Te mando la invitación con vuestra directora comercial.", "block"),
    # A statement before the question is still a statement (Dani, A22: «asegura algo no demostrado»).
    ("aafe089b", 162.0, "answer", "objection:custom:se_integra_con_nuestro_crm",
     "Con Excel no hay integración que montar: ¿qué campos tendríais que quedar apuntados solos?", "block"),
    # The four cards the 3.4 check wrongly blocked in the evaluation (reviewed by Dani as good or likely good).
    # Open for Dani: he forwards it to his director; does that back inviting her to the meeting?
    ("e4f9b418", 402.7, "move", "demo", "Perfecto, mañana a las 9:30. ¿Te mando la invitación con la directora comercial?", "?"),
    ("0c439183", 143.5, "answer", "objection:custom:enviame_un_correo",
     "Te la mando hoy, pero entre tú y yo, 15 minutos en directo te lo enseño funcionando. ¿Cuándo tienes un hueco?", "pass"),
    # Open for Dani: «quizás de cara al año que viene» and the card says «lo retomamos en enero» as if agreed.
    ("0c439183", 449.1, "move", "objection:custom:llama_el_mes_que_viene", "Perfecto, lo retomamos en enero. ¿Te llamo la primera semana?", "?"),
    ("9a12f59e", 212.0, "answer", "objection:custom:enviame_un_correo",
     "Te lo mando hoy. ¿A quién de marketing o IT se lo reenvías para revisarlo juntos 15 minutos?", "pass"),
    # A question that offers to show a capability takes it for granted (turns-1, Excel/Payper): it needs the source.
    ("aafe089b", 85.0, "move", "context", "Perfecto, con eso ya tengo lo que necesito: ¿te enseño en 15 minutos el jueves cómo rellenar esos campos sin que los toquen tus comerciales?", "block"),
    ("aafe089b", 139.0, "move", "context", "Te entiendo. Solo una cosa antes de colgar: ¿te enseño en 15 minutos el jueves cómo quedaría el Excel actualizado solo, y decides?", "block"),
    ("aafe089b", 139.0, "move", "context", "Te entiendo. ¿Te lo enseño 15 minutos el jueves y decides tú?", "pass"),
    # Stated as done, or a detail confirmed that differs from theirs (turns-4, Jaime and Blanca).
    ("9f125ca1", 520.0, "move", "context", "Listo, te acaba de llegar la invitación para el martes 20 a las 10:00; ¿lo vemos tú y alguien más?", "block"),
    ("281116db", 410.0, "move", "context", "Perfecto, lunes a las 10, te mando la invitación y lo vemos 15 minutos.", "block"),
    ("281116db", 410.0, "move", "context", "Perfecto, lunes a las 11, te mando la invitación y lo vemos 15 minutos.", "pass"),
    # Must pass: a proposal states nothing; naming the tool they use is not a claim about it.
    ("916d1bd8-real", 465, "move", "context", "Perfecto, te mando el mail. ¿Te va bien el martes a las 10?", "pass"),
    ("ea5cb466-real", 161, "answer", "objection:custom:ya_tenemos_gong",
     "Genial. ¿Qué parte usáis más de Granola: preparar, la reunión o el seguimiento?", "pass"),
    ("916d1bd8-real", 26, "answer", "offer",
     "Vocify ayuda al comercial antes, durante y después de sus reuniones: prepara, resuelve objeciones en directo y actualiza el CRM.", "pass"),
]


# (objective, earlier card, said since, expected changed): the state check behind the same-objective dedupe.
STATE_CASES = [
    ("agree a demo date", "¿Te enseño 15 minutos el jueves con vuestro caso?",
     "Other side: Yo creo que ya más o menos se ha podido ver. Sí, sí, sí, sí, total. Súper, qué bueno.", False),
    ("agree a demo date", "¿Te enseño 15 minutos el jueves con vuestro caso?",
     "Other side: mándame un mail, mándame un mail, ¿sabes? Porque ahora no es buen momento.", True),
    ("agree a demo date", "¿Te enseño 15 minutos el jueves con vuestro caso?", "Other side: el jueves no puedo, ¿el viernes por la mañana?", True),
    ("get intro to the AI lead", "¿Me pasas con la persona que lleva la parte de IA?",
     "Seller: claro, claro.\nOther side: vale.\nSeller: entonces, como te decía, la herramienta se conecta al CRM.", False),
    ("get intro to the AI lead", "¿Me pasas con la persona que lleva la parte de IA?",
     "Other side: eso lo tendría que ver Marcos, del equipo financiero, que es quien lo decide.", True),
    ("explain the product", "Vocify ayuda al comercial antes, durante y después de cada reunión.", "Other side: Mhm. Vale. Claro.", False),
]


# (last turns, expected closing): the end of the call as a state of the conversation, either side.
CLOSING_CASES = [
    ("Other side: Sí, sí, a partir de febrero de 2027, el proyecto tiene que haber entrado en otra fase.\nSeller: Vale, vale, perfecto, pues te deseo mucha suerte.\nOther side: Más me va, más me vale. Gracias,", True),
    ("Seller: ¿tú crees que es eso?\nOther side: Tío, mándame un mail y a ver si te podemos ver la semana que viene, ¿ok? Venga, hasta luego, tío.", True),
    # The salesperson closing is enough, before the other side answers (NeuronUP 9:52: a card right after it).
    ("Other side: Sí, sí, a partir de febrero de 2027, el proyecto tiene que haber entrado en otra fase.\nSeller: Vale, vale, perfecto, pues te deseo mucha suerte.", True),
    ("Seller: Perfecto, pues que vaya muy bien, un abrazo.\nOther side: Oye, espera, una cosa: ¿esto funciona con Zoho?", False),
    ("Other side: Perfecto, gracias por la info. Y otra cosa, ¿cuánto cuesta para un equipo de cinco?", False),
    ("Seller: Entonces el martes a las 10, ¿te va bien?\nOther side: Perfecto.\nSeller: Y oye, ¿cuántos comerciales sois ahora mismo?", False),
    ("Other side: Venga, hasta luego.\nSeller: ¡Espera! Una última cosa sobre el precio.\nOther side: Dime, dime.", False),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--runs", default="", help="replays whose well-written lines must still pass")
    parser.add_argument("--verdicts", default="", help="the judge's verdicts for those replays, same order")
    args = parser.parse_args()
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    from evals.copilot.run import load_production_provider

    load_production_provider()
    from evals.strategic import run_v2 as b
    from evals.strategic.run import context_for

    calls = {c: json.loads((CALLS / f"{c}.local.json").read_text(encoding="utf-8"))
             for c in ("1778148f-real", "916d1bd8-real", "ea5cb466-real", "e4f9b418", "0c439183", "9a12f59e", "aafe089b", "9f125ca1", "281116db")}
    sources = {c: context_for({**v, "playbook_version_id": None}) for c, v in calls.items()}
    cases = list(CASES)
    # Every line a judge found correct and usable: the check must not start blocking good help.
    for run, verdict in zip(filter(None, args.runs.split(",")), filter(None, args.verdicts.split(","))):
        good = {v["id"] for v in json.loads(Path(verdict).read_text(encoding="utf-8"))["cards"] if v["frase_util"]}
        for p in json.loads(Path(run).read_text(encoding="utf-8"))["played"]:
            for k, s in enumerate(sorted(p["shown"], key=lambda s: s["visible_t"]), 1):
                if f"{p['id'].replace('-real', '')}-T{k}" in good:
                    cases.append((p["id"], s["visible_t"], s["kind"], s.get("source") or "context", s["say"], "pass", s.get("source_quote", "")))
    wrong = 0
    for case in cases:
        cid, at, act, source, line, expected = case[:6]
        turns = calls[cid]["turns"]
        card = {"act": act, "source": source, "source_quote": case[6] if len(case) > 6 else "", "say": line}
        card["authorized"] = b.authorized_text(sources[cid], card)
        out = b.fact_check(card, "fact-cases", b.conversation_lines(turns, ends(turns), at, n=b.FACT_TURNS, chars=b.FACT_CHARS))["parsed"] or {"unsupported": True, "what": "check failed"}
        got = "block" if out["unsupported"] else "pass"
        if expected == "?":  # a case whose right answer is still the company's to decide: shown, not counted
            print(f"??? open  -> {got:5} {out['what'][:38]:38} | {line[:90]}")
            continue
        wrong += got != expected
        print(f"{'OK ' if got == expected else 'MAL'} {expected:5} -> {got:5} {out['what'][:38]:38} | {line[:90]}")
    counted = [c for c in cases if c[5] != "?"]
    print(f"\n{len(counted) - wrong} of {len(counted)} fact cases as expected ({len(cases) - len(counted)} open)")
    state_wrong = 0
    for objective, earlier, since, expected in STATE_CASES:
        got = [(b.state_check(objective, earlier, since, f"state-cases-{k}")["parsed"] or {"changed": None})["changed"] for k in range(3)]
        state_wrong += any(g != expected for g in got)
        print(f"{'OK ' if all(g == expected for g in got) else 'MAL'} changed={expected!s:5} -> {got} | {since[:80]}")
    print(f"{len(STATE_CASES) - state_wrong} of {len(STATE_CASES)} state cases as expected (three times each)")
    closing_wrong = 0
    for last, expected in CLOSING_CASES:
        got = [(b.closing_check(last, f"closing-cases-{k}")["parsed"] or {"closing": None})["closing"] for k in range(3)]
        closing_wrong += any(g != expected for g in got)
        print(f"{'OK ' if all(g == expected for g in got) else 'MAL'} closing={expected!s:5} -> {got} | {last[-80:]}")
    print(f"{len(CLOSING_CASES) - closing_wrong} of {len(CLOSING_CASES)} closing cases as expected (three times each)")
    state_wrong += closing_wrong
    return 1 if wrong or state_wrong else 0


if __name__ == "__main__":
    raise SystemExit(main())
