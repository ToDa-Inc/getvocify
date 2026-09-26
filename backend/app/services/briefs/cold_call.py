"""Cold-call brief lines from CRM profile, Hoy priority and playbook. No model call."""

from __future__ import annotations

from app.services.briefs.v2 import MAX_LINES, _day_label, _line
from app.services.briefs.preparation import prepare_brief

HUBSPOT_ANALYTICS_SOURCE = {
    "ORGANIC_SEARCH": "búsqueda orgánica",
    "PAID_SEARCH": "búsqueda de pago",
    "EMAIL_MARKETING": "email marketing",
    "SOCIAL_MEDIA": "redes sociales",
    "REFERRALS": "referido",
    "OTHER_CAMPAIGNS": "otra campaña",
    "DIRECT_TRAFFIC": "tráfico directo",
    "OFFLINE": "lead offline",
    "PAID_SOCIAL": "redes de pago",
}
HUBSPOT_LEAD_SOURCE = {
    "WEBFORM": "formulario web",
    "IMPORT": "importación",
    "WALK_IN": "visita",
    "TRADE_SHOW": "feria",
    "REFERRAL": "referido",
    "COLD_CALL": "llamada en frío",
    "EMAIL": "email",
    "ADVERTISEMENT": "anuncio",
}


def translate_crm_source(*, provider: str | None, analytics_source, lead_source) -> str | None:
    """Known CRM origin values in short Spanish; unknown values are omitted."""
    name = (provider or "").strip().lower()
    if name == "hubspot":
        for value in (lead_source, analytics_source):
            if not value:
                continue
            key = str(value).strip().upper()
            label = HUBSPOT_LEAD_SOURCE.get(key) or HUBSPOT_ANALYTICS_SOURCE.get(key)
            if label:
                return f"lead de {label}" if key in HUBSPOT_LEAD_SOURCE else label
        return None
    if name == "pipedrive":
        if lead_source:
            text = " ".join(str(lead_source).split())
            return f"lead de {text.lower()}" if text else None
        return None
    return None


def who_line(profile: dict | None, *, tz_name: str) -> dict | None:
    if not profile:
        return None
    role = " ".join(str(profile.get("jobtitle") or "").split())
    company = " ".join(str(profile.get("company_name") or "").split())
    source = " ".join(str(profile.get("source_label") or "").split())
    created = profile.get("created_at")
    day = _day_label(created, tz_name) if created else None

    head = f"{role} en {company}" if role and company else role or company
    tail_parts = []
    if source:
        tail_parts.append(source)
    if day:
        tail_parts.append(day)
    if not head and not tail_parts:
        return None
    text = head
    if tail_parts:
        text = f"{head} · {', '.join(tail_parts)}" if head else ", ".join(tail_parts)
    return _line("who", text, source_ref=profile.get("source_ref"), observed_at=created)


def why_line_cold(*, crm_task: dict | None, hoy_why: dict | None) -> dict | None:
    if crm_task and crm_task.get("text"):
        return _line(
            "why",
            str(crm_task["text"]),
            source_ref=crm_task.get("source_ref"),
            observed_at=crm_task.get("observed_at"),
        )
    if hoy_why and hoy_why.get("text"):
        return _line(
            "why",
            str(hoy_why["text"]),
            source_ref=hoy_why.get("source_ref"),
            observed_at=hoy_why.get("observed_at"),
        )
    return None


def open_line(steps: list[dict] | None, *, sales_motion_key: str | None) -> dict | None:
    if not sales_motion_key or not steps:
        return None
    for step in steps:
        if not isinstance(step, dict):
            continue
        if str(step.get("step_id") or "") != "opening":
            continue
        phrase = " ".join(str(step.get("reference_phrase") or step.get("reference") or "").split())
        if not phrase:
            continue
        return _line("open", phrase, source="playbook", source_ref=step.get("step_id"))
    return None


def prepare_cold_brief_v2(
    *,
    coverage: str,
    profile: dict | None,
    tz_name: str,
    crm_task: dict | None = None,
    hoy_why: dict | None = None,
    playbook_steps: list[dict] | None = None,
    sales_motion_key: str | None = None,
) -> dict:
    failed = coverage in {"partial", "unavailable"}
    notice = "No se pudo cargar todo." if failed else None
    if coverage == "unavailable":
        return {"status": "unavailable", "text": notice, "lines": [], "notice": notice, "label": None}

    lines: list[dict] = []
    who = who_line(profile, tz_name=tz_name)
    if who:
        lines.append(who)
    why = why_line_cold(crm_task=crm_task, hoy_why=hoy_why)
    if why:
        lines.append(why)
    opening = open_line(playbook_steps, sales_motion_key=sales_motion_key)
    if opening:
        lines.append(opening)
    lines = lines[:MAX_LINES]

    if coverage == "partial":
        return {"status": "partial", "text": notice, "lines": lines, "notice": notice, "label": None}

    if not lines:
        legacy = prepare_brief(coverage="complete", crm_task=crm_task)
        return {**legacy, "label": None}

    return {"status": "ready", "text": None, "lines": lines, "notice": None, "label": None}
