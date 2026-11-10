"""Write synthetic calls for a company's playbook, to play through the live brain (live_brain_run.py) before real calls exist.

    cd backend && python -m evals.copilot.synthetic_calls --user-id <rep uuid> --motion <call type> --n 50 --prefix syn-movertis

A model (Sonnet via OpenRouter) writes each call from one scenario: the rep follows the published playbook loosely and the
prospect is one kind of buyer from the company's ICP. Scenarios cover every objection and question the playbook answers,
each said clearly once and once in a way that is not that clear (half said, mixed with their situation, in passing), plus
calls with no objection, situation statements that only look like objections, vague pains, questions the company's
knowledge does not answer, two objections in one turn and heavy transcription noise. Each call carries `expected`: the
prospect turns the scenario means as an objection or a question (and which playbook answer it is for), written by the same
model, so they are the scenario's intention, not a person's label.

Writes `calls/<prefix>-NN.local.json` in the format live_brain_run reads. Reads the playbook from whatever SUPABASE_URL points
at (backend/.env: production); writes nothing to the database. The calls are invented: they say whether the brain recognises
and answers what the playbook covers, not how it behaves on a real, messy call.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from app.config import settings

OUT = Path(__file__).with_name("calls")
MODEL = "anthropic/claude-sonnet-5.5"
MS_PER_WORD, GAP_S = 0.33, 0.26

OTHER_SCENARIOS = [
    ("positive", "Interesado de verdad: cuenta su situación, hace alguna pregunta normal y acepta la reunión. Ninguna objeción."),
    ("positive", "Muy colaborador pero con prisa; da datos (flota, proveedor) y quiere que le manden la propuesta tras la reunión. Ninguna objeción."),
    ("positive", "Escéptico al principio pero sin objetar: pregunta cómo funciona y acaba agendando. Ninguna objeción."),
    ("positive", "Ya conoce Movertis por un colega; quiere ver precios en la reunión. Ninguna objeción."),
    ("trap", "Describe mucho su situación (número de vehículos, que tienen GPS, que alquilan a empresas) sin poner ninguna pega: son datos, no objeciones."),
    ("trap", "Dice cosas que suenan negativas sobre su propio negocio («este año ha sido flojo», «tenemos poca gente») pero no contra la llamada ni Movertis."),
    ("trap", "Habla de su proveedor actual de GPS solo para contestar a la pregunta del comercial, contento pero abierto a escuchar."),
    ("trap", "Pregunta retórica y pensando en voz alta («¿cómo lo hacemos ahora? pues a mano, la verdad»), sin objetar."),
    ("deepen", "Menciona de pasada un dolor vago («las devoluciones son un caos», «perdemos dinero con los kilómetros») sin dar causa, caso ni cifra."),
    ("deepen", "Se queja vagamente de un cliente que no pagaba y siguió usando el vehículo, sin detalles."),
    ("deepen", "Dice que los mantenimientos y la documentación «se les escapan» sin dar ejemplos."),
    ("unknown", "Pregunta algo que la empresa probablemente no tiene escrito: si los datos se guardan en Europa y quién tiene acceso."),
    ("unknown", "Pregunta si hay una app para los conductores/clientes que alquilan y si funciona sin cobertura."),
    ("unknown", "Pregunta cuánto tarda la instalación por vehículo y si la hace un técnico en sus instalaciones."),
    ("double", "En un mismo turno: ya tienen proveedor Y además ahora no es el momento."),
    ("double", "En un mismo turno: pide que le manden información por email Y dice que eso lo decide su socio."),
    ("noise", "Llamada con transcripción muy ruidosa: frases cortadas, palabras mal transcritas, repeticiones, «eh», el prospecto se interrumpe; mete una objeción de precio a medias."),
    ("noise", "Llamada con transcripción muy ruidosa y el prospecto conduciendo («te escucho mal»); acaba diciendo que le llamen en otro momento."),
]

SYSTEM = """You write realistic Spanish (Spain) phone calls for testing a sales assistant. Output only JSON.
The call is a cold call by an SDR of the company below to a prospect from its ICP. The rep follows the playbook loosely, in
their own words (never reading the examples word for word), and does NOT always answer objections well. The prospect is a real
person: short turns, interruptions, filler words («eh», «vale», «mira»), sometimes long turns. 10 to 22 turns in total. The
call starts with the rep. Write it as it would come out of a speech-to-text transcript (no stage directions, no names in the
text). Never make the rep invent facts about the company that the context does not give.

Output: {"turns": [{"who": "you"|"them", "text": string}], "expected": [{"turn": index in turns (a "them" turn), "kind":
"objection"|"question"|"deepen", "entry_id": the playbook answer id it is for, or null, "note": at most 8 words}]}.
"expected" lists ONLY the prospect turns the scenario means as an objection, a question to answer, or a vague pain worth
digging into. A call with none has "expected": []."""


def _post(prompt: str) -> dict:
    response = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"},
        json={"model": MODEL, "temperature": 0.9, "max_tokens": 8000, "response_format": {"type": "json_object"},
              "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]},
        timeout=180,
    )
    response.raise_for_status()
    text = response.json()["choices"][0]["message"]["content"]
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start : end + 1])


def scenarios(entries: list[dict], n: int) -> list[dict]:
    """Every playbook answer clearly and not that clearly, then the other kinds, cut or repeated to `n`."""
    out = []
    for entry in entries:
        name = entry.get("label") or entry.get("category")
        said = f' (they say things like «{entry["trigger"]}»)' if entry.get("trigger") else ""
        base = {"entry_id": entry["entry_id"], "name": name}
        out.append({**base, "kind": "clear", "brief": f"El prospecto pone claramente la objeción/pregunta «{name}»{said}, una vez, a mitad de llamada."})
        out.append({**base, "kind": "unclear", "brief": (
            f"El prospecto pone la objeción/pregunta «{name}» de forma NADA clara: a medias, mezclada con su situación, de pasada o "
            "con rodeos, sin la frase típica; un comercial atento la notaría, uno despistado no.")})
    out += [{"entry_id": None, "name": kind, "kind": kind, "brief": brief} for kind, brief in OTHER_SCENARIOS]
    random.Random(7).shuffle(out)
    while len(out) < n:
        out += out[: n - len(out)]
    return out[:n]


def with_times(turns: list[dict]) -> list[dict]:
    out, t = [], 0.0
    for i, turn in enumerate(turns):
        text = " ".join(str(turn.get("text") or "").split())
        if not text or turn.get("who") not in ("you", "them"):
            continue
        out.append({"id": f"t{len(out)}", "who": turn["who"], "text": text, "t": round(t, 1), "_src": i})
        t += len(text.split()) * MS_PER_WORD + GAP_S
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--motion", required=True)
    parser.add_argument("--icp-motion", help="a playbook of the company that describes its buyer (its steps are read as the ICP)")
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--call-mode", default="softphone")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    from app.api import copilot as api
    from app.deps import get_supabase
    from app.services.company import CompanyService
    from app.services.copilot.live_models import LiveReading

    sb = get_supabase()
    membership = CompanyService(sb).require_membership(args.user_id)
    stub = LiveReading(call_id="synthetic", call_mode=args.call_mode, sales_motion_key=args.motion, turns=[{"id": "t0", "who": "you", "text": "Hola", "t": 0}])
    ctx = asyncio.run(api._brain_context(sb, membership, stub))
    if not ctx.snapshot:
        print(f"no published playbook for {args.motion}", file=sys.stderr)
        return 1
    snapshot = ctx.snapshot
    icp = ""
    if args.icp_motion:
        icp_stub = stub.model_copy(update={"sales_motion_key": args.icp_motion})
        icp_ctx = asyncio.run(api._brain_context(sb, membership, icp_stub))
        icp = "\n".join(f"- {s.get('label')}: {s.get('criterion')}" for s in (icp_ctx.snapshot or {}).get("steps") or [])
    entries = [e for e in snapshot.get("entries") or [] if isinstance(e, dict) and e.get("entry_id") and str(e.get("guidance") or "").strip()]
    playbook = json.dumps({"steps": snapshot.get("steps"), "answers": entries, "to_find_out": snapshot.get("qualification")}, ensure_ascii=False)
    context = (
        f"COMPANY OFFER:\n{ctx.product_context[:6000]}\n\nCOMPANY KNOWLEDGE:\n{json.dumps(ctx.knowledge, ensure_ascii=False)[:6000]}\n\n"
        f"ICP / BUYER (what the playbook says about the buyer and their pains):\n{icp or '(not given)'}\n\nPLAYBOOK:\n{playbook}"
    )
    plan = scenarios(entries, args.n)
    OUT.mkdir(exist_ok=True)

    def write(item: tuple[int, dict]) -> str:
        n, scenario = item
        prompt = (
            f"{context}\n\nSCENARIO ({scenario['kind']}): {scenario['brief']}\n"
            + (f"The playbook answer this is about has id {scenario['entry_id']}.\n" if scenario["entry_id"] else "")
            + "Pick a different kind of rental company (size, vehicles, clients) from the ICP for this call."
        )
        for attempt in range(3):
            try:
                raw = _post(prompt)
                turns = with_times(raw.get("turns") or [])
                if len(turns) < 6:
                    raise ValueError("too short")
                index = {t["_src"]: t["id"] for t in turns}
                expected = [
                    {"turn": index[e["turn"]], "kind": e.get("kind"), "entry_id": e.get("entry_id"), "note": e.get("note")}
                    for e in raw.get("expected") or [] if isinstance(e, dict) and e.get("turn") in index
                ]
                for t in turns:
                    t.pop("_src")
                call_id = f"{args.prefix}-{n:02d}"
                (OUT / f"{call_id}.local.json").write_text(json.dumps({
                    "id": call_id, "user_id": args.user_id, "company_id": membership.company_id, "motion": args.motion,
                    "call_mode": args.call_mode, "playbook_version_id": ctx.playbook_version_id, "synthetic": True,
                    "scenario": scenario, "expected": expected, "turns": turns,
                }, ensure_ascii=False, indent=1), encoding="utf-8")
                return f"{call_id} {scenario['kind']} {scenario['name']}: {len(turns)} turns, {len(expected)} expected"
            except Exception as exc:  # a bad answer from the model: ask again
                last = exc
        return f"FAILED {n:02d} {scenario['kind']} {scenario['name']}: {last}"

    with ThreadPoolExecutor(args.workers) as pool:
        for line in pool.map(write, enumerate(plan, 1)):
            print(line, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
