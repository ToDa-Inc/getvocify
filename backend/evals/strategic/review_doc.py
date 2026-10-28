"""The review document for Dani: per reference moment, what was said, his label, and what each system showed in each run,
with the helper model's verdict next to it (a first filter, not the judge).

    cd backend && python -m evals.strategic.review_doc --score scores.json --name A=A-r1.json,A-r2.json --name B=B-r1.json \
        --out evals/copilot/calls/revision.md

Customer speech: write it only under evals/copilot/calls/ (gitignored).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.strategic.run import CALLS

ORDER = {"critico": 0, "intervenir": 1, "preferido": 2, "opcional": 3, "silencio": 4}
VERDICT = {"matches": "da la ayuda esperada", "fine": "razonable, no la esperada", "bad": "mala aquí"}


def clock(t: float) -> str:
    return f"{int(t // 60)}:{int(t % 60):02d}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--score", required=True, help="score_moments output for every run named below")
    parser.add_argument("--name", action="append", required=True, help="SYSTEM=run1.json,run2.json")
    parser.add_argument("--moments", default=str(CALLS / "momentos-referencia.local.json"))
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    score = json.loads(Path(args.score).read_text(encoding="utf-8"))
    systems = {}
    for spec in args.name:
        name, files = spec.split("=", 1)
        systems[name] = files.split(",")
    moments = sorted(json.loads(Path(args.moments).read_text(encoding="utf-8")), key=lambda m: (ORDER[m["dani"]], m["call"], m["id"]))
    rows = {path: {r["moment"]: r for r in rep["rows"]} for path, rep in score.items()}
    runs = {path: {p["id"]: p for p in json.loads(Path(path).read_text(encoding="utf-8"))["played"]} for path in score}

    def key_for(f: str) -> str:
        return next(p for p in score if p.endswith(Path(f).name))

    out = ["# Revisión por momento", "",
           "Para cada momento: lo que se dijo, tu etiqueta, y lo que vio el comercial con cada sistema en cada ronda. "
           "Al lado, la opinión del modelo ayudante (un primer filtro, no el juez). Marca donde no estés de acuerdo.", ""]
    for name, files in systems.items():
        sums = [score[key_for(f)]["summary"] for f in files]
        out.append(f"- **{name}**: " + " · ".join(
            f"ronda {k + 1}: intervenir {s['must_hit']}, críticos {s['critical_hit']}, silencio con ruido {s['silence_noise']}, "
            f"{s['cards_per_10_min']} tarjetas/10 min, ${s['cost_per_30_min']}/30 min" for k, s in enumerate(sums)))
    out.append("")
    for m in moments:
        turns = json.loads((CALLS / f"{m['call']}.local.json").read_text(encoding="utf-8"))["turns"]
        idx = {t["id"]: i for i, t in enumerate(turns)}
        lo, hi = idx[m["from"]], idx[m["to"]]
        out += [f"## {m['id']} · {m['dani']} · {m['what']}", ""]
        if m.get("expected"):
            out.append(f"Esperado: {m['expected']}" + (f" · Malo: {m['bad']}" if m.get("bad") else ""))
            out.append("")
        for t in turns[max(0, lo - 2):hi + 1]:
            out.append(f"> {clock(t['t'])} **{'Cliente' if t['who'] == 'them' else 'Comercial'}**: {' '.join(t['text'].split())[:300]}")
        out.append("")
        for name, files in systems.items():
            for k, f in enumerate(files):
                path = key_for(f)
                row = rows[path].get(m["id"])
                if not row:
                    continue
                cards = row["inside"] + (row["later"] if m["dani"] in ("critico", "intervenir", "preferido") else [])
                if not cards:
                    out.append(f"- {name} r{k + 1}: (nada) → {row['result']}")
                    continue
                for i in cards:
                    s = runs[path][m["call"]]["shown"][i]
                    c = row["checks"].get(str(i)) or row["checks"].get(i) or {}
                    late = " (tarde)" if i in row["later"] else ""
                    who = "rápido" if s.get("producer") == "fast" else ("respuesta" if s.get("kind") == "answer" else "jugada")
                    out.append(f"- {name} r{k + 1} {clock(s['visible_t'])}{late} [{who}] «{s['say']}» → {VERDICT.get(c.get('verdict'), '?')}"
                               f"{'' if c.get('sayable', True) else ', no se dice de un vistazo'}"
                               f"{', contenido incorrecto' if c.get('quality') == 'wrong' else ''} ({c.get('why', '')})")
                out.append(f"  resultado r{k + 1}: {row['result']}")
        out.append("")
    out += ["# Tarjetas fuera de tus momentos (el ayudante no las juzga)", ""]
    for name, files in systems.items():
        path = key_for(files[0])
        out.append(f"## {name}, ronda 1")
        for u in score[path]["unlabelled"]:
            out.append(f"- {u['call']} {clock(u['at'])}: {u['card']}")
        out.append("")
    Path(args.out).write_text("\n".join(out), encoding="utf-8")
    print("written", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
