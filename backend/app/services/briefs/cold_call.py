"""Cold-call brief lines from the CRM profile and the Hoy priority reason. No model call."""

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
    "OFFLINE": "fuente offline",
    "PAID_SOCIAL": "redes de pago",
}
# Priority reasons a Hoy card labels (shared/ui/hoy-copy.js). Others have no card wording to reuse.
HOY_CARD_REASONS = frozenset({"no_calls_logged", "pain_agree_next_step"})


def hubspot_source_label(value) -> str | None:
    """Documented `hs_analytics_source` values in short Spanish; anything else is omitted."""
    if not value:
        return None
    return HUBSPOT_ANALYTICS_SOURCE.get(str(value).strip().upper())


def who_line(profile: dict | None, *, tz_name: str) -> dict | None:
    if not profile:
        return None
    role = " ".join(str(profile.get("jobtitle") or "").split())
    company = " ".join(str(profile.get("company_name") or "").split())
    source = " ".join(str(profile.get("source_label") or "").split())
    created = profile.get("created_at")
    day = _day_label(created, tz_name) if created else None

    head = f"{role} en {company}" if role and company else role or company
    tail = ", ".join(part for part in (source, day) if part)
    if not head and not tail:
        return None
    text = f"{head} · {tail}" if head and tail else head or tail
    return _line("who", text, source_ref=profile.get("source_ref"), observed_at=created)


def why_line_cold(
    *,
    crm_task: dict | None,
    hoy_priority: dict | None,
    created_at=None,
    tz_name: str,
) -> dict | None:
    """The CRM task, else the Hoy reason key. The client words the key with Hoy's own copy."""
    if crm_task and crm_task.get("text"):
        return _line(
            "why",
            str(crm_task["text"]),
            source_ref=crm_task.get("source_ref"),
            observed_at=crm_task.get("observed_at"),
        )
    reason = str((hoy_priority or {}).get("reason") or "")
    if reason not in HOY_CARD_REASONS:
        return None
    since = _day_label(created_at, tz_name) if reason == "no_calls_logged" and created_at else None
    return {
        "type": "why",
        "text": None,
        "reason": reason,
        "since": since,
        "source_ref": hoy_priority.get("source_ref"),
        "observed_at": hoy_priority.get("observed_at"),
    }


def prepare_cold_brief_v2(
    *,
    coverage: str,
    profile: dict | None,
    tz_name: str,
    crm_task: dict | None = None,
    hoy_priority: dict | None = None,
) -> dict:
    failed = coverage in {"partial", "unavailable"}
    notice = "No se pudo cargar todo." if failed else None
    if coverage == "unavailable":
        return {"status": "unavailable", "text": notice, "lines": [], "notice": notice, "label": None}

    lines: list[dict] = []
    who = who_line(profile, tz_name=tz_name)
    if who:
        lines.append(who)
    why = why_line_cold(
        crm_task=crm_task,
        hoy_priority=hoy_priority,
        created_at=(profile or {}).get("created_at"),
        tz_name=tz_name,
    )
    if why:
        lines.append(why)
    lines = lines[:MAX_LINES]

    if coverage == "partial":
        return {"status": "partial", "text": notice, "lines": lines, "notice": notice, "label": None}

    if not lines:
        legacy = prepare_brief(coverage="complete", crm_task=crm_task)
        return {**legacy, "label": None}

    return {"status": "ready", "text": None, "lines": lines, "notice": None, "label": None}
