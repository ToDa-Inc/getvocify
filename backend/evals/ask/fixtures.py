"""Seeded company for the Ask eval. Synthetic on purpose: no customer data, known ground truth.

Reps: Ana (u-ana, an account executive), Luis (u-luis), Marta (u-marta). Dani (u-dev) owns the account.
`TRUTH` holds the numbers an answer must reproduce.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.hubspot.call_log import HUBSPOT_DISPOSITION_GUID as G
from app.services.hubspot.types import CRMSchema, HubSpotProperty, PropertyOption
from tests.crm_copilot.fakes import FakeCompanyService, FakeHubSpotClient, FakeSupabase

NOW = datetime.now(timezone.utc)
COMPANY = "co-eval"
REPS = {"u-ana": ("Ana Ruiz", "101"), "u-luis": ("Luis Prieto", "102"), "u-marta": ("Marta Gil", "103"), "u-dev": ("Dani", "100")}


def _iso(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


def _ev(memo_id: str, quote: str, speaker: str) -> dict:
    return {"id": "ev-" + hashlib.sha1(f"{memo_id}{quote}".encode()).hexdigest()[:8], "source_type": "transcript", "source_id": memo_id, "quote": quote, "speaker_role": speaker}


def memo(mid, user, contact, name, company, days, summary, *, interest="medium", objs=(), commits=(), meeting=None, competitors=(), pains=(), analysed=True, screening=None):
    evidence, episodes, promises = [], [], []
    for kind, cat, res, quote, reply in objs:
        q = _ev(mid, quote, "prospect")
        evidence.append(q)
        item = {"kind": kind, "category": cat, "resolution": res, "quote": quote, "evidence_refs": [q["id"]]}
        if reply:
            r = _ev(mid, reply, "rep")
            evidence.append(r)
            item.update(response=reply, response_evidence=r["id"])
        episodes.append(item)
    for text, due_in_days, quote in commits:
        q = _ev(mid, quote, "rep")
        evidence.append(q)
        promises.append({"kind": "send", "origin": "rep_promise", "text": text, "due_at": _iso(-due_in_days), "evidence_refs": [q["id"]]})
    extraction = {"summary": summary, "contactName": name, "companyName": company, "painPoints": list(pains), "competitors": list(competitors), "nextSteps": [c[0] for c in commits]}
    if analysed:
        extraction["intelligence"] = {
            "version": 1, "input_revision": "r", "status": "ready", "prompt_version": "intelligence_v2", "interest": interest,
            "objections": episodes, "commitments": promises,
            "meeting": {"agreed": meeting, "evidence_refs": []}, "competitor_mentions": [{"name": c} for c in competitors],
            "playbook_observations": [], "evidence": evidence,
        }
    row = {
        "id": mid, "user_id": user, "company_id": COMPANY, "status": "approved", "hubspot_contact_id": contact,
        "created_at": _iso(days), "capture_started_at": _iso(days), "interaction_kind": "call", "screening_outcome": screening,
        "extraction": extraction, "transcript": "Them: x",
    }
    if analysed:
        # The real revision, so "is this memo analysed?" behaves exactly as it does in production.
        from app.services.intelligence.worker import revision_for_memo

        extraction["intelligence"]["input_revision"] = revision_for_memo(row)
    return row


P, T, A, C, S, TR = "price", "timing", "authority", "competitor", "status_quo", "trust"
OB, OBS = "objection", "obstacle"

MEMOS = [
    # Ana: account executive
    memo("m01", "u-ana", "c-marina", "Marina López", "Acme", 3, "Marina quiere automatizar el seguimiento comercial.", interest="high",
         objs=[(OB, P, "open", "Nos parece caro para el equipo", None), (OBS, "bad_moment", "resolved", "Ahora estoy conduciendo", "Te llamo mañana a las diez")],
         commits=[("enviar el caso de logística", 1, "Te envío el caso de logística mañana")], meeting=None, pains=["Seguimiento manual: unas 3 h a la semana"]),
    memo("m02", "u-ana", "c-marina", "Marina López", "Acme", 11, "Primera llamada con Marina: descubrimiento.", interest="medium",
         objs=[(OB, C, "open", "Ahora usamos Gong", None)], competitors=["Gong"], meeting=True, pains=["No saben qué leads llamar primero"]),
    memo("m03", "u-ana", "c-pablo", "Pablo Ortega", "Logística Sur", 5, "Pablo pide precio y compara con un competidor.", interest="high",
         objs=[(OB, P, "resolved", "El precio se nos va de presupuesto", "Te muestro el retorno en tres meses y lo comparamos")], competitors=["Salesloft"], meeting=True),
    memo("m04", "u-ana", "c-ines", "Inés Vidal", "Textil Norte", 15, "Inés estaba interesada, sin novedades desde entonces.", interest="high", meeting=None),
    memo("m05", "u-ana", "c-ines", "Inés Vidal", "Textil Norte", 22, "Llamada inicial con Inés.", interest="medium", objs=[(OBS, "gatekeeper", "resolved", "Le paso con ella, un momento", None)]),
    memo("m06", "u-ana", "c-hugo", "Hugo Sanz", "Tecno 3", 2, "Hugo no era la persona adecuada.", interest="low", objs=[(OBS, "wrong_person", "open", "Eso lo lleva mi compañera de compras", None)], meeting=False),
    memo("m07", "u-ana", "c-elena", "Elena Cruz", "Fresh Food", 8, "Elena dice que ya usan una hoja de cálculo.", interest="low", objs=[(OB, S, "open", "Con el Excel nos apañamos", None)], meeting=False),
    memo("m08", "u-ana", "c-nuria", "Nuria Pons", "Clínica Sol", 6, "Nuria quiere consultarlo con su socio.", interest="medium", objs=[(OBS, "needs_to_consult", "open", "Tengo que verlo con mi socio", None)]),
    memo("m09", "u-ana", "c-oscar", "Óscar Mena", "Ferretería Mena", 4, "Sin resultado: buzón.", analysed=False, screening="voicemail"),
    # Luis
    memo("m10", "u-luis", "c-jorge", "Jorge Alba", "BioFarm", 2, "Jorge duda del precio frente a HubSpot Sales Hub.", interest="medium",
         objs=[(OB, P, "open", "El precio es alto para lo que hacemos", None), (OB, C, "open", "Ya tenemos HubSpot Sales Hub", None)], competitors=["HubSpot Sales Hub"]),
    memo("m11", "u-luis", "c-lucia", "Lucía Marín", "Retail 24", 9, "Lucía acepta una demo.", interest="high", meeting=True, commits=[("mandar la invitación de la demo", -2, "Te mando la invitación de la demo")]),
    memo("m12", "u-luis", "c-ivan", "Iván Roca", "Cimientos SL", 13, "Iván pide más tiempo.", interest="medium", objs=[(OB, T, "open", "Ahora no es prioridad, quizá el año que viene", None)]),
    memo("m13", "u-luis", "c-sara", "Sara Bel", "Aula Viva", 7, "Sara no responde al precio.", interest="low", objs=[(OB, P, "open", "No tenemos presupuesto este trimestre", None)], meeting=False),
    memo("m14", "u-luis", "c-tomas", "Tomás Gil", "Hotel Mar", 3, "Llamada corta, mal momento.", interest="medium", objs=[(OBS, "bad_moment", "open", "Estoy en una reunión, llámame luego", None)]),
    memo("m15", "u-luis", "c-vera", "Vera Sol", "Estudio V", 19, "Vera desconfía de los resultados.", interest="low", objs=[(OB, TR, "open", "No me fío de que funcione con nuestro volumen", None)]),
    memo("m16", "u-luis", "c-yago", "Yago Rey", "Motor Rey", 30, "Antigua, sin análisis.", analysed=False),
    # Marta
    memo("m17", "u-marta", "c-raul", "Raúl Nieto", "Cimientos Nieto", 4, "Raúl dice que decide su director.", interest="medium", objs=[(OB, A, "open", "La decisión la toma mi director", None)], meeting=None),
    memo("m18", "u-marta", "c-eva", "Eva Luna", "Luna Studio", 6, "Eva pide precio y acepta reunión.", interest="high", objs=[(OB, P, "resolved", "Es más caro que lo que pagamos hoy", "Empezamos con un piloto de un mes y medimos")], meeting=True),
    memo("m19", "u-marta", "c-dario", "Darío Vega", "Vega Gráficas", 10, "Darío usa Gong.", interest="low", objs=[(OB, C, "open", "Ya estamos con Gong", None)], competitors=["Gong"], meeting=False),
    memo("m20", "u-marta", "c-carla", "Carla Ríos", "Ríos Consulting", 12, "Carla acepta una reunión.", interest="high", meeting=True),
    memo("m21", "u-marta", "c-mario", "Mario Paz", "Paz Logística", 5, "Recepción no pasa la llamada.", interest="low", objs=[(OBS, "gatekeeper", "open", "El señor Paz no atiende llamadas comerciales", None)]),
    memo("m22", "u-marta", "c-lola", "Lola Nieto", "Nieto Bebidas", 8, "Lola pide propuesta, precio pendiente.", interest="high", objs=[(OB, P, "open", "Necesito ver el precio antes de nada", None)], commits=[("enviar la propuesta", 2, "Te mando la propuesta el jueves")]),
    memo("m23", "u-marta", "c-pepe", "Pepe Roca", "Roca Muebles", 1, "Reciente, aún sin analizar.", analysed=False),
    memo("m24", "u-marta", "c-rosa", "Rosa Diaz", "Diaz Ropa", 17, "Rosa se enfrió tras la demo.", interest="high", meeting=True),
]

CONTACTS = {m["hubspot_contact_id"]: {"id": m["hubspot_contact_id"], "name": m["extraction"]["contactName"], "company": m["extraction"]["companyName"]} for m in MEMOS}


def _ms(y, mo, d, hour=11) -> str:
    return str(int(datetime(y, mo, d, hour, tzinfo=timezone.utc).timestamp() * 1000))


# Calls are spread over the working day (UTC; Madrid is +2 in summer). Connected calls cluster in the late morning.
_HOURS_CONNECTED = (8, 8, 9, 14)
_HOURS_OTHER = (7, 8, 9, 10, 12, 13, 14, 15)


def _calls(owner: str, y: int, mo: int, outcomes: dict) -> list[dict]:
    rows, day = [], 1
    for outcome, n in outcomes.items():
        for _ in range(n):
            hour = (_HOURS_CONNECTED if outcome == "connected" else _HOURS_OTHER)[len(rows) % (4 if outcome == "connected" else 8)]
            props = {"hs_timestamp": _ms(y, mo, day, hour), "hubspot_owner_id": owner, "hs_call_direction": "OUTBOUND"}
            if outcome != "unknown":
                props["hs_call_disposition"] = G[outcome]
            if outcome == "connected":
                props["hs_call_duration"] = str(60_000 + (len(rows) % 6) * 45_000)  # 1:00 to 4:45, in milliseconds
            rows.append(props)
            day = day % 27 + 1
    return rows


CALLS = (
    _calls("101", 2026, 8, {"connected": 15, "no_answer": 30, "voicemail": 8, "busy": 2, "unknown": 5})
    + _calls("102", 2026, 8, {"connected": 9, "no_answer": 28, "voicemail": 7, "busy": 3, "unknown": 3})
    + _calls("103", 2026, 8, {"connected": 12, "no_answer": 16, "voicemail": 6, "busy": 2, "unknown": 4})
    + _calls("101", 2026, 7, {"connected": 10, "no_answer": 20, "voicemail": 5})
    + _calls("101", 2026, 9, {"connected": 6, "no_answer": 11, "voicemail": 3})
)


def _deals(owner: str, y: int, mo: int, lost: dict, won: int) -> list[dict]:
    rows = []
    for reason, n in lost.items():
        for _ in range(n):
            p = {"closedate": _ms(y, mo, 10), "hs_is_closed_lost": "true", "hs_is_closed_won": "false", "hubspot_owner_id": owner}
            if reason != "none":
                p["closed_lost_reason"] = reason
            rows.append(p)
    rows += [{"closedate": _ms(y, mo, 12), "hs_is_closed_lost": "false", "hs_is_closed_won": "true", "hubspot_owner_id": owner} for _ in range(won)]
    return rows


DEALS = (
    _deals("101", 2026, 8, {"price": 4, "no_budget": 2, "competitor": 1, "none": 1}, 4)
    + _deals("102", 2026, 8, {"price": 3, "no_budget": 3, "timing": 2, "no_decision": 1, "none": 1}, 2)
    + _deals("103", 2026, 8, {"price": 2, "competitor": 3, "timing": 1, "no_decision": 1, "none": 1}, 2)
    + _deals("101", 2026, 9, {"price": 1, "no_budget": 1}, 1)
)


# ----- the rest of the portal: pipeline, meetings, tasks, contacts ------------------------------------------------

STAGES = [
    ("appointmentscheduled", "Appointment Scheduled"), ("qualifiedtobuy", "Qualified To Buy"),
    ("presentationscheduled", "Presentation Scheduled"), ("decisionmakerboughtin", "Decision Maker Bought-In"),
    ("contractsent", "Contract Sent"), ("closedwon", "Closed Won"), ("closedlost", "Closed Lost"),
]
PIPELINES = [{"id": "default", "label": "Sales Pipeline", "archived": False, "stages": [{"id": i, "label": l} for i, l in STAGES]}]


def _open_deal(n, owner, stage, amount, created_month, created_day, segment, last_activity_days_ago):
    return {
        "id": f"od{n}", "dealname": f"Oportunidad {n}", "hubspot_owner_id": owner, "dealstage": stage, "pipeline": "default", "amount": str(amount),
        "createdate": _ms(2026, created_month, created_day), "hs_is_closed_won": "false", "hs_is_closed_lost": "false", "segmento": segment,
        "notes_last_updated": str(int((datetime.now(timezone.utc) - timedelta(days=last_activity_days_ago)).timestamp() * 1000)),
    }


OPEN_DEALS = [
    _open_deal(1, "101", "appointmentscheduled", 4000, 8, 3, "pyme", 4), _open_deal(2, "101", "qualifiedtobuy", 9000, 8, 9, "pyme", 12),
    _open_deal(3, "101", "presentationscheduled", 15000, 8, 15, "enterprise", 2), _open_deal(4, "101", "contractsent", 32000, 7, 20, "enterprise", 40),
    _open_deal(5, "102", "appointmentscheduled", 2500, 8, 5, "pyme", 55), _open_deal(6, "102", "qualifiedtobuy", 7000, 8, 12, "pyme", 9),
    _open_deal(7, "102", "decisionmakerboughtin", 21000, 7, 8, "enterprise", 3), _open_deal(8, "102", "contractsent", 18000, 8, 22, "pyme", 33),
    _open_deal(9, "103", "qualifiedtobuy", 6000, 8, 2, "pyme", 6), _open_deal(10, "103", "presentationscheduled", 12000, 9, 4, "enterprise", 1),
    _open_deal(11, "103", "decisionmakerboughtin", 27000, 8, 18, "enterprise", 61), _open_deal(12, "103", "appointmentscheduled", 3500, 9, 10, "pyme", 5),
]
for _d in DEALS:  # the closed deals: a stage and an amount, so revenue questions have something to add up
    _d.setdefault("dealstage", "closedwon" if _d["hs_is_closed_won"] == "true" else "closedlost")
    _d.setdefault("pipeline", "default")
    _d.setdefault("createdate", str(int(_d["closedate"]) - 30 * 86_400_000))
    if _d["hs_is_closed_won"] == "true":
        _d.setdefault("amount", str(5000 + (int(_d["closedate"]) // 86_400_000) % 4 * 1000))
DEALS = DEALS + OPEN_DEALS


def _meeting(n, owner, day, outcome):
    return {"id": f"mt{n}", "hs_timestamp": _ms(2026, 8, day), "hubspot_owner_id": owner, "hs_meeting_outcome": outcome}


MEETINGS = (
    [_meeting(i, "101", 3 + i, "COMPLETED") for i in range(5)] + [_meeting(10, "101", 20, "NO_SHOW")]
    + [_meeting(20 + i, "102", 4 + i, "COMPLETED") for i in range(3)] + [_meeting(30, "102", 21, "NO_SHOW"), _meeting(31, "102", 22, "NO_SHOW")]
    + [_meeting(40 + i, "103", 5 + i, "COMPLETED") for i in range(4)]
)


def _task(n, owner, days_from_now, status):
    return {"id": f"tk{n}", "hs_timestamp": str(int((datetime.now(timezone.utc) + timedelta(days=days_from_now)).timestamp() * 1000)), "hubspot_owner_id": owner, "hs_task_status": status, "hs_task_subject": f"Tarea {n}"}


TASKS = (
    [_task(1, "101", -3, "NOT_STARTED"), _task(2, "101", -1, "NOT_STARTED"), _task(3, "101", 2, "NOT_STARTED"), _task(4, "101", -5, "COMPLETED")]
    + [_task(5, "102", -9, "NOT_STARTED"), _task(6, "102", -2, "NOT_STARTED"), _task(7, "102", -4, "NOT_STARTED"), _task(8, "102", 1, "NOT_STARTED")]
    + [_task(9, "103", 3, "NOT_STARTED"), _task(10, "103", -7, "COMPLETED")]
)


def _contact(n, owner, source, month, day):
    return {"id": f"ct{n}", "hubspot_owner_id": owner, "hs_analytics_source": source, "createdate": _ms(2026, month, day), "lifecyclestage": "lead"}


CONTACT_ROWS = (
    [_contact(i, "101", "ORGANIC_SEARCH", 8, 2 + i) for i in range(6)] + [_contact(10 + i, "101", "PAID_SEARCH", 8, 3 + i) for i in range(3)]
    + [_contact(20 + i, "102", "REFERRALS", 8, 5 + i) for i in range(4)] + [_contact(30 + i, "102", "ORGANIC_SEARCH", 8, 9 + i) for i in range(2)]
    + [_contact(40 + i, "103", "DIRECT_TRAFFIC", 8, 4 + i) for i in range(5)] + [_contact(50, "103", "PAID_SEARCH", 7, 15)]
    + [{**_contact(60 + i, "", "REFERRALS", 7, 5 + i)} for i in range(4)]  # no owner: created in July
)
for _c in CONTACT_ROWS:
    if not _c["hubspot_owner_id"]:
        _c.pop("hubspot_owner_id")


def _prop(name, label, type_="string", options=None, description=None, **extra):
    return {"name": name, "label": label, "type": type_, "options": [{"label": l, "value": v} for v, l in (options or [])], "hubspotDefined": True, "description": description or "", **extra}


SCHEMAS = {
    "deals": [
        _prop("dealname", "Deal Name"), _prop("amount", "Amount", "number", description="The total value of the deal in the deal's currency"),
        _prop("dealstage", "Deal Stage", "enumeration"), _prop("pipeline", "Pipeline", "enumeration"),
        _prop("createdate", "Create Date", "datetime"), _prop("closedate", "Close Date", "datetime"),
        _prop("hs_is_closed_won", "Is Closed Won", "bool", [("true", "True"), ("false", "False")]),
        _prop("hs_is_closed_lost", "Is Closed Lost", "bool", [("true", "True"), ("false", "False")]),
        _prop("closed_lost_reason", "Motivo de pérdida", "enumeration", [("price", "Precio"), ("no_budget", "Sin presupuesto"), ("competitor", "Competidor"), ("timing", "Momento"), ("no_decision", "Sin decisión")]),
        _prop("notes_last_updated", "Last Activity Date", "datetime", description="The last time a note, call, meeting, or task was logged for a record"),
        _prop("hubspot_owner_id", "Deal owner", "enumeration"),
        _prop("segmento", "Segmento", "enumeration", [("pyme", "Pyme"), ("enterprise", "Enterprise")], hubspotDefined=False),
    ],
    "calls": [
        _prop("hs_timestamp", "Activity date", "datetime"), _prop("hs_call_disposition", "Call outcome", "enumeration"),
        _prop("hs_call_direction", "Call direction", "enumeration", [("INBOUND", "Inbound"), ("OUTBOUND", "Outbound")]),
        _prop("hs_call_duration", "Call duration", "number", description="The duration of the call in milliseconds"),
        _prop("hubspot_owner_id", "Activity assigned to", "enumeration"),
    ],
    "meetings": [
        _prop("hs_timestamp", "Activity date", "datetime"),
        _prop("hs_meeting_outcome", "Meeting outcome", "enumeration", [("SCHEDULED", "Scheduled"), ("COMPLETED", "Completed"), ("RESCHEDULED", "Rescheduled"), ("NO_SHOW", "No show"), ("CANCELED", "Canceled")]),
        _prop("hubspot_owner_id", "Activity assigned to", "enumeration"),
    ],
    "tasks": [
        _prop("hs_timestamp", "Due date", "datetime"), _prop("hs_task_subject", "Title"),
        _prop("hs_task_status", "Task Status", "enumeration", [("NOT_STARTED", "Not started"), ("IN_PROGRESS", "In progress"), ("WAITING", "Waiting"), ("COMPLETED", "Completed"), ("DEFERRED", "Deferred")]),
        _prop("hubspot_owner_id", "Assigned to", "enumeration"),
    ],
    "contacts": [
        _prop("createdate", "Create Date", "datetime"),
        _prop("hs_analytics_source", "Original Source", "enumeration", [("ORGANIC_SEARCH", "Organic Search"), ("PAID_SEARCH", "Paid Search"), ("REFERRALS", "Referrals"), ("DIRECT_TRAFFIC", "Direct Traffic"), ("SOCIAL_MEDIA", "Social Media")]),
        _prop("lifecyclestage", "Lifecycle Stage", "enumeration", [("lead", "Lead"), ("opportunity", "Opportunity"), ("customer", "Customer")]),
        _prop("hubspot_owner_id", "Contact owner", "enumeration"),
    ],
    "companies": [_prop("createdate", "Create Date", "datetime"), _prop("hubspot_owner_id", "Company owner", "enumeration")],
}


def _month_calls(owner=None):
    lo, hi = int(datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp() * 1000), int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp() * 1000)
    return [c for c in CALLS if lo <= int(c["hs_timestamp"]) < hi and (owner is None or c["hubspot_owner_id"] == owner)]


def _rate(rows):
    connected = sum(1 for c in rows if c.get("hs_call_disposition") == G["connected"])
    return len(rows), connected, round(connected * 100 / len(rows), 1)


def _aug_deals(owner=None):
    lo, hi = int(datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp() * 1000), int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp() * 1000)
    return [d for d in DEALS if d.get("closedate") and lo <= int(d["closedate"]) < hi and (owner is None or d["hubspot_owner_id"] == owner)]


def _held_out(open_deals, won_aug, calls_aug, contacts_aug) -> dict:
    """Truths for questions written after the tools were built, to see how far they generalise."""
    ent = [int(d["amount"]) for d in open_deals if d.get("segmento") == "enterprise"]
    longest = max(int(c.get("hs_call_duration") or 0) for c in calls_aug)
    minutes, seconds = divmod(longest // 1000, 60)
    stage_sum = lambda stage: sum(int(d["amount"]) for d in open_deals if d["dealstage"] == stage)  # noqa: E731
    open_tasks = lambda owner: sum(1 for t in TASKS if t["hs_task_status"] != "COMPLETED" and t["hubspot_owner_id"] == owner)  # noqa: E731
    return {
        "unowned_contacts": sum(1 for c in CONTACT_ROWS if not c.get("hubspot_owner_id")),
        "won_aug_count": len(won_aug), "won_aug_amount": sum(int(d["amount"]) for d in won_aug),
        "longest_call_readable": f"{minutes}m {seconds:02d}s", "longest_call_minutes": minutes, "longest_call_seconds": seconds,
        "pipeline_qualified": stage_sum("qualifiedtobuy"), "pipeline_contract_sent": stage_sum("contractsent"),
        "open_deals_per_rep": sum(1 for d in open_deals if d["hubspot_owner_id"] == "101"),
        "ana_organic_contacts_aug": sum(1 for c in contacts_aug if c.get("hubspot_owner_id") == "101" and c["hs_analytics_source"] == "ORGANIC_SEARCH"),
        "referrals_share_aug": round(sum(1 for c in contacts_aug if c["hs_analytics_source"] == "REFERRALS") * 100 / len(contacts_aug), 1),
        "enterprise_open_avg": round(sum(ent) / len(ent)),
        "open_tasks_ana": open_tasks("101"), "open_tasks_luis": open_tasks("102"), "open_tasks_marta": open_tasks("103"),
    }


def _shares(open_deals, calls_aug, aug) -> dict:
    from zoneinfo import ZoneInfo

    madrid = ZoneInfo("Europe/Madrid")
    by_hour: dict[int, list[int]] = {}
    for c in calls_aug:
        hour = datetime.fromtimestamp(int(c["hs_timestamp"]) / 1000, madrid).hour
        cell = by_hour.setdefault(hour, [0, 0])
        cell[0] += 1
        cell[1] += c.get("hs_call_disposition") == G["connected"]
    ranked = sorted(((hit * 100 / n, hour) for hour, (n, hit) in by_hour.items() if n >= 10), reverse=True)
    july = [c for c in CALLS if int(datetime(2026, 7, 1, tzinfo=timezone.utc).timestamp() * 1000) <= int(c["hs_timestamp"]) < int(datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp() * 1000)]
    over = sum(1 for c in calls_aug if int(c.get("hs_call_duration") or 0) > 120_000)
    ms = lambda y, m: int(datetime(y, m, 1, tzinfo=timezone.utc).timestamp() * 1000)  # noqa: E731
    made = lambda m: [d for d in DEALS if ms(2026, m) <= int(d["createdate"]) < ms(2026, m + 1)]  # noqa: E731
    sep_calls = [c for c in CALLS if ms(2026, 9) <= int(c["hs_timestamp"]) < ms(2026, 10)]
    return {
        "team_rate_sep": round(sum(1 for c in sep_calls if c.get("hs_call_disposition") == G["connected"]) * 100 / len(sep_calls), 1),
        "deals_created_aug": len(made(8)), "deals_created_sep": len(made(9)),
        "deals_created_change_pct": round((len(made(9)) - len(made(8))) * 100 / len(made(8)), 1),
        "pct_calls_over_2min_aug": round(over * 100 / len(calls_aug), 1),
        "calls_jul": len(july), "calls_change_vs_jul_pct": round((len(calls_aug) - len(july)) * 100 / len(july), 1),
        "contract_sent_open": sum(1 for d in open_deals if d["dealstage"] == "contractsent"),
        "contract_sent_share_pct": round(sum(1 for d in open_deals if d["dealstage"] == "contractsent") * 100 / len(open_deals), 1),
        "best_hour_aug": ranked[0][1], "best_hour_aug_rate": round(ranked[0][0], 1), "second_hour_aug_rate": round(ranked[1][0], 1),
    }


def _portal_truth() -> dict:
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    aug = lambda rows, key="hs_timestamp": [r for r in rows if int(datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp() * 1000) <= int(r[key]) < int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp() * 1000)]  # noqa: E731
    open_deals = [d for d in DEALS if d["hs_is_closed_won"] == "false" and d["hs_is_closed_lost"] == "false"]
    won_aug = [d for d in aug([d for d in DEALS if d.get("closedate")], "closedate") if d["hs_is_closed_won"] == "true"]
    calls_aug = aug([c for c in CALLS if c["hs_call_direction"] == "OUTBOUND"])
    connected_aug = [c for c in calls_aug if c.get("hs_call_disposition") == G["connected"]]
    overdue = [t for t in TASKS if t["hs_task_status"] != "COMPLETED" and int(t["hs_timestamp"]) < now_ms]
    contacts_aug = aug(CONTACT_ROWS, "createdate")
    return {
        "open_deals": len(open_deals), "open_value": sum(int(d["amount"]) for d in open_deals),
        "ana_open_value": sum(int(d["amount"]) for d in open_deals if d["hubspot_owner_id"] == "101"),
        "enterprise_open_value": sum(int(d["amount"]) for d in open_deals if d.get("segmento") == "enterprise"),
        "qualified_open": sum(1 for d in open_deals if d["dealstage"] == "qualifiedtobuy"),
        "biggest_open_amount": max(int(d["amount"]) for d in open_deals),
        "stale_open_deals": sum(1 for d in open_deals if now_ms - int(d["notes_last_updated"]) > 30 * 86_400_000),
        "avg_won_amount_aug": round(sum(int(d["amount"]) for d in won_aug) / len(won_aug)),
        "calls_over_2min_aug": sum(1 for c in calls_aug if int(c.get("hs_call_duration") or 0) > 120_000),
        "avg_connected_seconds_aug": round(sum(int(c["hs_call_duration"]) for c in connected_aug) / len(connected_aug) / 1000),
        "meetings_aug": len(aug(MEETINGS)), "ana_meetings_aug": sum(1 for m in aug(MEETINGS) if m["hubspot_owner_id"] == "101"), "meetings_completed_aug": sum(1 for m in aug(MEETINGS) if m["hs_meeting_outcome"] == "COMPLETED"),
        "no_shows_aug": sum(1 for m in aug(MEETINGS) if m["hs_meeting_outcome"] == "NO_SHOW"),
        "luis_no_shows_aug": sum(1 for m in aug(MEETINGS) if m["hs_meeting_outcome"] == "NO_SHOW" and m["hubspot_owner_id"] == "102"),
        "overdue_tasks": len(overdue), "ana_overdue_tasks": sum(1 for t in overdue if t["hubspot_owner_id"] == "101"),
        "contacts_aug": len(contacts_aug), "organic_contacts_aug": sum(1 for c in contacts_aug if c["hs_analytics_source"] == "ORGANIC_SEARCH"),
        **_shares(open_deals, calls_aug, aug),
        **_held_out(open_deals, won_aug, calls_aug, contacts_aug),
        "calls_week_1_aug": sum(1 for c in calls_aug if int(datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp() * 1000) <= int(c["hs_timestamp"]) < int(datetime(2026, 8, 8, tzinfo=timezone.utc).timestamp() * 1000)),
    }


def _truth() -> dict:
    ana, team = _rate(_month_calls("101")), _rate(_month_calls())
    lost = [d for d in _aug_deals() if d["hs_is_closed_lost"] == "true"]
    won = [d for d in _aug_deals() if d["hs_is_closed_won"] == "true"]
    ana_lost = [d for d in _aug_deals("101") if d["hs_is_closed_lost"] == "true"]
    return {
        "ana_calls_aug": ana[0], "ana_connected_aug": ana[1], "ana_rate_aug": ana[2],
        "team_calls_aug": team[0], "team_connected_aug": team[1], "team_rate_aug": team[2],
        "luis_calls_aug": _rate(_month_calls("102"))[0], "luis_rate_aug": _rate(_month_calls("102"))[2],
        "marta_rate_aug": _rate(_month_calls("103"))[2],
        "lost_aug": len(lost), "won_aug": len(won), "win_rate_aug": round(len(won) * 100 / (len(won) + len(lost)), 1),
        "price_lost_aug": sum(1 for d in lost if d.get("closed_lost_reason") == "price"),
        "ana_lost_aug": len(ana_lost), "ana_price_lost_aug": sum(1 for d in ana_lost if d.get("closed_lost_reason") == "price"),
        **_portal_truth(),
    }


TRUTH = _truth()

PLAYBOOK = dict(
    playbooks=[{"id": "p1", "company_id": COMPANY, "sales_motion_key": "discovery", "active_version_id": "v1"}],
    playbook_versions=[{
        "id": "v1", "playbook_id": "p1", "status": "published",
        "steps": [{"label": "Confirmar el problema"}, {"label": "Identificar al decisor"}, {"label": "Acordar siguiente paso"}],
        "entries": [
            {"entry_id": "e-price", "category": "price", "approved_answer": "Antes de dar precio, pregunta cuánto les cuesta hoy el problema y compara con el retorno a tres meses."},
            {"entry_id": "e-comp", "category": "competitor", "approved_answer": "No ataques al competidor: pregunta qué le falta a su herramienta y propón un piloto de un mes en paralelo."},
            {"entry_id": "e-time", "category": "timing", "approved_answer": "Fija una fecha concreta de revisión y envía un resumen de una línea."},
            {"entry_id": "e-auth", "category": "authority", "approved_answer": "Pide que te presente al decisor y prepara con tu contacto el argumento para él."},
        ],
    }],
)

OWNERS = [{"id": rid, "firstName": n.split()[0], "lastName": " ".join(n.split()[1:]), "email": f"{uid}@eval.test"} for uid, (n, rid) in REPS.items()]


_SCORED = ["m01", "m03", "m10", "m11", "m17", "m18", "m20", "m22"]
SCORES = [
    {"memo_id": mid, "created_at": _iso(0.02), "score": {"status": "ready", "met_steps": met, "missed_steps": miss, "unknown_steps": 0, "not_applicable_steps": 0}}
    for mid, met, miss in zip(_SCORED, [4, 3, 4, 2, 4, 3, 4, 3], [0, 1, 0, 2, 0, 1, 0, 1])
]


TRUTH["adherence_pct"] = round(sum(r["score"]["met_steps"] for r in SCORES) * 100 / sum(r["score"]["met_steps"] + r["score"]["missed_steps"] for r in SCORES), 1)


# What the Coaching screen and the Head of Sales screen compute, fixed here so their producers (tested upstream) are not
# re-run against a toy database. The eval judges what Ask does with them: which tool, what it says, what it refuses to say.
COACHING_ANA = {
    "flow": "sdr", "available_flows": ["sdr"], "motion": "discovery", "week_start": "2026-09-28", "playbook_published": True,
    "numbers": {"conversations": 12, "meetings_agreed": 3, "process_complete": 5, "interactions": 20},
    "prev_numbers": {"conversations": 10, "meetings_agreed": 2, "process_complete": 4, "interactions": 18},
    "steps": [
        {"step_id": "s1", "label": "Confirmar el problema", "rate": 0.4, "prev_rate": 0.25, "peer_median": 0.7},
        {"step_id": "s2", "label": "Identificar al decisor", "rate": 0.75, "prev_rate": 0.7, "peer_median": 0.6},
        {"step_id": "s3", "label": "Acordar siguiente paso", "rate": 0.6, "prev_rate": 0.55, "peer_median": 0.65},
    ],
    "focus": {
        "step_id": "s1", "label": "Confirmar el problema", "criterion": "Nombra el problema con las palabras del prospecto antes de presentar nada.",
        "example": None, "why": {"rate": 0.25, "applicable": 8, "missing": 6, "peer_median": 0.7},
        "week_total": {"done": 2, "applicable": 5, "rate": 0.4}, "achieved": False, "progress": [],
    },
    "conversion": {"complete_rate": 0.5, "incomplete_rate": 0.2, "complete_n": 6, "incomplete_n": 9},
}


def _rep(uid, focus_label, focus_rate, attempts, connected, meetings):
    return {
        "userId": uid, "name": REPS[uid][0], "salesRole": "sdr", "activity": {"attempts": attempts, "connected": connected, "meetings": meetings},
        "coaching_focus": {"step_id": "s", "label": focus_label, "rate": focus_rate}, "flows": {"sdr": None, "ae": None},
    }


TEAM_BODY = {
    "adherence": 0.58, "met_steps": 29, "applicable_steps": 50,
    "sample_limited": False, "attempts": 90, "connected": 28, "meetings": 9,
    "period": {"start": "2026-08-30T00:00:00+00:00", "end": "2026-09-29T00:00:00+00:00"},
    "previous": {"adherence": 0.5, "attempts": 70, "connected": 20, "meetings": 6},
    "process_health": [{
        "motion": "discovery", "goal": "meeting_booked", "verdict": "coach_reps", "scored": 40, "follow_share": 0.4,
        "follows_goal_rate": 0.55, "deviates_goal_rate": 0.2, "needed": 0,
    }],
    "reps": [
        _rep("u-ana", "Confirmar el problema", 0.25, 30, 9, 3), _rep("u-luis", "Identificar al decisor", 0.3, 32, 10, 3),
        _rep("u-marta", "Acordar siguiente paso", 0.45, 28, 9, 3),
    ],
    "objection_categories": [{"name": "price", "count": 6, "open": 3, "resolved": 3, "unknown": 0}, {"name": "competitor", "count": 3, "open": 3, "resolved": 0, "unknown": 0}],
}
TRUTH.update({
    "adherence_pct": 58.0, "adherence_change_pts": 8.0, "ana_focus_week_pct": 40.0,
    "ana_focus_rate_pct": 25.0, "ana_focus_conversations": 8, "ana_focus_missed": 6, "focus_team_median_pct": 70.0,
    "conversion_full_pct": 50.0, "conversion_gaps_pct": 20.0,
    "team_follow_share_pct": 40.0, "team_follows_goal_pct": 55.0, "team_gaps_goal_pct": 20.0, "team_adherence_prev_pct": 50.0,
})


def build_db() -> FakeSupabase:
    return FakeSupabase(memos=[dict(m) for m in MEMOS], memo_scores=[dict(r) for r in SCORES], **PLAYBOOK)


def build_bundle() -> SimpleNamespace:
    schema = CRMSchema(
        object_type="deals",
        properties=[HubSpotProperty(
            name="closed_lost_reason", label="Motivo de pérdida", type="enumeration", options=[
                PropertyOption(label="Precio", value="price"), PropertyOption(label="Sin presupuesto", value="no_budget"),
                PropertyOption(label="Competidor", value="competitor"), PropertyOption(label="Momento", value="timing"),
                PropertyOption(label="Sin decisión", value="no_decision"),
            ])],
    )

    async def get_deal_schema(use_cache=True):
        return schema

    return SimpleNamespace(
        client=FakeHubSpotClient(calls=CALLS, deals=DEALS, owners=OWNERS, records={"meetings": MEETINGS, "tasks": TASKS, "contacts": CONTACT_ROWS}, schema=SCHEMAS, pipelines=PIPELINES),
        connection={"id": "conn-eval", "provider": "hubspot", "metadata": {"hubspot_owners": {uid: rid for uid, (_n, rid) in REPS.items()}}},
        provider=SimpleNamespace(_schema_service=lambda: SimpleNamespace(get_deal_schema=get_deal_schema)),
    )


def build_company() -> FakeCompanyService:
    service = FakeCompanyService(list(REPS))
    service.list_members = lambda company_id: [  # type: ignore[method-assign]
        {"user_id": uid, "status": "active", "full_name": name, "email": f"{uid}@eval.test"} for uid, (name, _r) in REPS.items()
    ]
    return service
