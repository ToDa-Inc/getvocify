"""The email of a report that has a digest (REPORT_FEEDBACK_ENABLED): the numbers as cards with the
change against the previous period, the "% del proceso" as a bar, the written feedback and, for the
Head of Sales, one row per rep. Table layout and inline styles only: what every mail client renders.
Every text from the data is escaped."""

from __future__ import annotations

from html import escape

INK = "#1f1d1a"
MUTED = "#6b6560"
LINE = "#e8e2da"
PAPER = "#f7f4ef"
CARD = "#ffffff"
ACCENT = "#6b4f2e"
GOOD = "#2f6b3a"
GOOD_BG = "#eef5ef"
WARN = "#8a5a12"
WARN_BG = "#fbf3e4"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"

PREVIOUS_WORD = {"day": "el día anterior", "week": "la semana pasada"}


def _pct(value) -> str | None:
    return None if value is None else f"{round(float(value) * 100)} %"


def _delta(now: int | None, before: int | None, period: str) -> str:
    if now is None or not before:
        return ""
    diff = now - before
    if diff == 0:
        text, color = f"igual que {PREVIOUS_WORD[period]}", MUTED
    else:
        text, color = f"{'+' if diff > 0 else '−'}{abs(diff)} vs {PREVIOUS_WORD[period]}", GOOD if diff > 0 else WARN
    return f'<div style="font-size:12px;color:{color};margin-top:4px">{escape(text)}</div>'


def _card(label: str, value: str, note: str = "") -> str:
    return (
        f'<td style="background:{CARD};border:1px solid {LINE};border-radius:10px;padding:14px 12px;'
        f'vertical-align:top;width:50%;word-wrap:break-word">'
        f'<div style="font-size:13px;color:{MUTED}">{escape(label)}</div>'
        f'<div style="font-size:24px;font-weight:700;color:{INK};margin-top:6px">{escape(value)}</div>{note}</td>'
    )


def _cards(digest: dict, period: str) -> str:
    act, prev = digest.get("activity") or {}, digest.get("previous") or {}
    coach = digest.get("coaching") or {}
    role = digest.get("sales_role") or "general"
    booked = act.get("meetings_booked")
    connect = _pct(act.get("connect_rate"))
    cards = []
    if role != "ae" or act.get("calls"):
        cards.append(_card("Llamadas", str(act.get("calls") or 0), _delta(act.get("calls"), prev.get("calls"), period)))
    cards.append(_card(
        "Conversaciones", str(act.get("conversations") or 0),
        (f'<div style="font-size:12px;color:{MUTED};margin-top:4px">{escape(connect)} de conexión</div>' if connect else "")
        + _delta(act.get("conversations"), prev.get("conversations"), period),
    ))
    if role != "sdr" and act.get("meetings_held"):
        cards.append(_card("Reuniones hechas", str(act["meetings_held"]), _delta(act["meetings_held"], prev.get("meetings_held"), period)))
    cards.append(_card(
        "Reuniones agendadas", "Sin marcar" if booked is None else str(booked),
        "" if booked is None else _delta(booked, prev.get("meetings_booked"), period),
    ))
    adherence = _pct(coach.get("adherence"))
    if len(cards) < 4:
        cards.append(_card("% del proceso", adherence or "—", f'<div style="font-size:12px;color:{MUTED};margin-top:4px">'
                           f'{int(coach.get("evaluated") or 0)} evaluadas</div>'))
    cards = cards[:4]
    spacer = '<td style="width:8px"></td>'
    rows = [cards[index:index + 2] for index in range(0, len(cards), 2)]
    body = '<tr><td colspan="3" style="height:8px"></td></tr>'.join(
        f"<tr>{spacer.join(pair)}{'' if len(pair) == 2 else spacer + '<td></td>'}</tr>" for pair in rows
    )
    return f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="table-layout:fixed">{body}</table>'


def _bar(label: str, value: float | None, right: str) -> str:
    width = 0 if value is None else max(2, min(100, round(float(value) * 100)))
    return (
        f'<tr><td style="font-size:13px;color:{INK};padding:6px 10px 6px 0;white-space:nowrap">{escape(label)}</td>'
        f'<td style="width:100%;padding:6px 0"><div style="background:{LINE};border-radius:6px;height:10px">'
        f'<div style="background:{ACCENT};border-radius:6px;height:10px;width:{width}%"></div></div></td>'
        f'<td style="font-size:13px;color:{MUTED};padding:6px 0 6px 10px;white-space:nowrap">{escape(right)}</td></tr>'
    )


def _process_block(digest: dict) -> str:
    coach = digest.get("coaching") or {}
    rows = []
    steps = coach.get("adherence_steps") or {}
    if coach.get("adherence") is not None:
        rows.append(_bar("% del proceso", coach["adherence"], f"{steps.get('met', 0)} de {steps.get('applicable', 0)} pasos"))
    by_type = coach.get("by_type") or {}
    total = sum(by_type.values())
    for label, count in sorted(by_type.items(), key=lambda item: -item[1]):
        rows.append(_bar(label, count / total if total else None, f"{count} conv."))
    if not rows:
        return ""
    return _section("Cómo fue el proceso", f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0">{"".join(rows)}</table>')


def _section(title: str, body: str) -> str:
    return (
        f'<tr><td style="padding:22px 0 0"><div style="font-size:15px;font-weight:700;color:{INK};margin-bottom:10px">'
        f'{escape(title)}</div>{body}</td></tr>'
    )


def _list(items: list[str], color: str, background: str) -> str:
    return "".join(
        f'<div style="background:{background};border-left:3px solid {color};border-radius:6px;padding:10px 12px;'
        f'margin-bottom:8px;font-size:14px;line-height:1.45;color:{INK}">{escape(item)}</div>'
        for item in items
    )


def _feedback_block(feedback: dict | None) -> str:
    if not feedback:
        return ""
    out = ""
    if feedback.get("went_well"):
        out += _section("Lo que salió bien", _list(feedback["went_well"], GOOD, GOOD_BG))
    if feedback.get("to_improve"):
        out += _section("Qué mejorar", _list(feedback["to_improve"], WARN, WARN_BG))
    if feedback.get("focus"):
        out += _section("Tu foco", (
            f'<div style="background:{INK};color:#fff;border-radius:10px;padding:14px 16px;font-size:15px;line-height:1.45">'
            f'{escape(feedback["focus"])}</div>'
        ))
    return out


def _objections_block(digest: dict) -> str:
    objections = (digest.get("coaching") or {}).get("objections") or []
    if not objections:
        return ""
    rows = "".join(
        f'<tr><td style="font-size:14px;color:{INK};padding:7px 0;border-bottom:1px solid {LINE}">{escape(str(item.get("label") or ""))}</td>'
        f'<td style="font-size:13px;color:{MUTED};padding:7px 0;border-bottom:1px solid {LINE};text-align:right;white-space:nowrap">'
        f'{int(item.get("total") or 0)} · {int(item.get("open") or 0)} sin resolver</td></tr>'
        for item in objections
    )
    return _section("Objeciones que te pusieron", f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0">{rows}</table>')


def _improvement_block(snapshot: dict, report_href: str) -> str:
    """The playbook answers that keep failing and the link to fix them (the Head of Sales' weekly report only)."""
    block = snapshot.get("playbook_improvement")
    items = block.get("items") if isinstance(block, dict) else None
    if not items:
        return ""
    rows = "".join(
        f'<tr><td style="font-size:14px;color:{INK};padding:7px 0;border-bottom:1px solid {LINE}">{escape(str(item.get("label") or ""))}</td>'
        f'<td style="font-size:13px;color:{MUTED};padding:7px 0;border-bottom:1px solid {LINE};text-align:right;white-space:nowrap">'
        f'{int(item.get("failing") or 0)} de {int(item.get("total") or 0)} sin éxito</td></tr>'
        for item in items
    )
    href = report_href.split("/dashboard/")[0] + str(block.get("link") or "")
    link = f'<p style="margin:12px 0 0"><a href="{escape(href)}" style="color:{ACCENT};font-size:14px;font-weight:600">Revisarlas en el playbook</a></p>'
    return _section("Respuestas que conviene afinar", f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0">{rows}</table>{link}')


ROLE_ES = {"sdr": "SDR", "ae": "AE", "general": "General"}


def _team_block(digest: dict, feedback: dict | None) -> str:
    """One card per rep: name and role, the week in one line, and the note on them."""
    reps = digest.get("reps") or []
    if not reps:
        return ""
    notes = {str(p.get("name") or "").casefold(): p.get("note") for p in (feedback or {}).get("people") or []}
    cards = ""
    for rep in reps:
        meetings = rep.get("meetings_held") or 0
        booked = rep.get("meetings_booked")
        facts = [f"{rep.get('calls') or 0} llamadas", f"{rep.get('conversations') or 0} conversaciones"]
        if meetings:
            facts.append(f"{meetings} reuniones hechas")
        facts.append("reuniones sin marcar" if booked is None else f"{booked} reuniones agendadas")
        if rep.get("adherence") is not None:
            facts.append(f"{_pct(rep['adherence'])} del proceso")
        note = notes.get(str(rep.get("name") or "").casefold()) or (f"Foco: {rep['top_slip']}" if rep.get("top_slip") else "")
        cards += (
            f'<div style="background:{CARD};border:1px solid {LINE};border-radius:10px;padding:12px 14px;margin-bottom:8px">'
            f'<div style="font-size:15px;font-weight:700;color:{INK}">{escape(str(rep.get("name") or ""))}'
            f' <span style="font-size:12px;font-weight:400;color:{MUTED}">{ROLE_ES.get(rep.get("sales_role"), "")}</span></div>'
            f'<div style="font-size:13px;color:{MUTED};margin-top:4px">{escape(" · ".join(facts))}</div>'
            + (f'<div style="font-size:14px;color:{INK};margin-top:8px;line-height:1.45">{escape(note)}</div>' if note else "")
            + "</div>"
        )
    return _section("Por comercial", cards)


def render(snapshot: dict, *, report_href: str, title: str) -> str:
    digest = snapshot.get("digest") or {}
    feedback = snapshot.get("feedback")
    period = "week" if snapshot.get("report_type") == "weekly" or snapshot.get("scope") == "team" else "day"
    headline = (feedback or {}).get("headline")
    team = snapshot.get("scope") == "team"
    rows = [
        f'<tr><td style="font-size:13px;color:{MUTED};text-transform:uppercase;letter-spacing:.06em">{escape(title)}</td></tr>',
        (f'<tr><td style="font-size:22px;font-weight:700;line-height:1.3;color:{INK};padding:6px 0 18px">{escape(headline)}</td></tr>'
         if headline else '<tr><td style="padding:6px 0 12px"></td></tr>'),
        f"<tr><td>{_cards(digest, period)}</td></tr>",
        _feedback_block(feedback),
        _team_block(digest, feedback) if team else "",
        _process_block(digest),
        _objections_block(digest),
        _improvement_block(snapshot, report_href),
        f'<tr><td style="padding:26px 0 0"><a href="{escape(report_href)}" style="display:inline-block;background:{ACCENT};'
        f'color:#fff;text-decoration:none;border-radius:999px;padding:11px 20px;font-size:14px;font-weight:600">Ver el informe completo</a></td></tr>',
    ]
    return (
        f'<div style="background:{PAPER};padding:24px 12px;font-family:{FONT}">'
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:600px;margin:0 auto;table-layout:fixed;word-wrap:break-word">'
        f'{"".join(rows)}</table></div>'
    )
