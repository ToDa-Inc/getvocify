"""Pre-call brief. Only facts. A missing conversation is not a failed read."""

from __future__ import annotations


def prepare_brief(
    *,
    coverage: str,
    last: dict | None = None,
    pending: dict | None = None,
    objection: dict | None = None,
    pain_confirmed: bool = False,
    crm_task: dict | None = None,
) -> dict:
    failed = coverage in {"partial", "unavailable"}
    notice = "No se pudo cargar todo." if failed else None
    if coverage == "unavailable":
        return {"status": "unavailable", "text": notice, "lines": [], "notice": notice}

    lines = _fact_lines(last, pending, objection)
    if coverage == "partial":
        return {"status": "partial", "text": notice, "lines": lines, "notice": notice}

    talked = last is not None or pending is not None or objection is not None
    if not talked:
        extra = []
        if crm_task and crm_task.get("text"):
            extra.append(_line("crm", crm_task["text"], crm_task.get("source_ref"), crm_task.get("observed_at")))
        return {
            "status": "no_conversation",
            "text": "Sin conversación todavía.",
            "lines": extra,
            "notice": None,
        }

    if last is not None and not pending and not objection and not pain_confirmed:
        day = str(last.get("observed_at") or "")[:10]
        return {
            "status": "nothing_pending",
            "text": f"Última vez: {day}. No quedó nada pendiente.",
            "lines": [],
            "notice": None,
        }

    return {"status": "ready", "text": None, "lines": lines, "notice": None}


def _fact_lines(last: dict | None, pending: dict | None, objection: dict | None) -> list[dict]:
    lines = []
    if last and last.get("text"):
        lines.append(_line("last", last["text"], last.get("source_ref"), last.get("observed_at")))
    if pending and pending.get("text"):
        lines.append(_line("pending", pending["text"], pending.get("source_ref"), pending.get("observed_at")))
    if objection and objection.get("text"):
        text = objection["text"]
        reply = (objection.get("playbook") or "").strip()
        if reply:
            text = f"{text} {reply}"
        lines.append(_line("objection", text, objection.get("source_ref"), objection.get("observed_at")))
    return lines[:3]


def _line(kind: str, text: str, source_ref, observed_at) -> dict:
    return {"type": kind, "text": text, "source_ref": source_ref, "observed_at": observed_at}
