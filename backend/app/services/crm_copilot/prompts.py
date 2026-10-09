from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _DIR / "skills"
_PROMPTS_DIR = _DIR.parents[1] / "prompts"

SOUL = (_DIR / "soul.md").read_text()
DATA_PROMPT_VERSION = "ask_vocify_data_v1"
DATA_PROMPT = (_PROMPTS_DIR / f"{DATA_PROMPT_VERSION}.md").read_text(encoding="utf-8")
ASK_PROMPT = (_DIR / "ask_prompt.md").read_text()
SKILL_BODIES = {
    path.stem: path.read_text()
    for path in sorted(_SKILL_DIR.glob("*.md"))
}


def with_data_prompt(system: str) -> str:
    """WhatsApp: the Vocify-data tools (flag ASK_VOCIFY_DATA_TOOLS_ENABLED) come with their routing rules."""
    data = DATA_PROMPT.strip()
    if data in system:
        return system
    soul = SOUL.strip()
    if system.startswith(soul):
        return f"{soul}\n\n{data}{system[len(soul):]}"
    return f"{system}\n\n{data}"


def _session_lines(artifacts: dict) -> list[str]:
    copilot = (artifacts or {}).get("copilot") or {}
    lines = []
    for key in ("last_contact_id", "last_company_id", "last_deal_id", "last_contact_url", "last_deal_url", "memo_id"):
        if copilot.get(key):
            lines.append(f"- {key}: {copilot[key]}")
    memory = copilot.get("memory") or []
    if memory:
        lines.append("Memory:")
        lines += [f"- {item}" for item in memory[-12:]]
    return lines


def _web_prompt(artifacts: dict, manager: bool, today: Optional[str], tz: str, team: Optional[dict]) -> str:
    audience = "a sales manager who can see the whole team" if manager else "an account executive who can see only their own work"
    limits = (
        "You may look at the whole team or at one person (user_id)."
        if manager
        else "This person can only see their own work: if asked about the team, another rep or who is best, say so in one sentence and call no tool."
    )
    roster = ""
    if team:
        people = "; ".join(f"{name} = {uid}" for uid, name in sorted(team.items(), key=lambda kv: kv[1].casefold()))
        roster = f"The team, and the only people who exist (use these ids for user_id): {people}.\n"
    text = (
        ASK_PROMPT.replace("{audience}", audience)
        .replace("{today}", today or datetime.now(timezone.utc).date().isoformat())
        .replace("{tz}", tz)
        .replace("{team}", roster)
        .replace("{limits}", limits)
        .strip()
    )
    session = _session_lines(artifacts)
    return text + ("\n\n# Session\n" + "\n".join(session) if session else "")


def build_system_prompt(
    artifacts: dict,
    *,
    data_tools: bool = False,
    web: bool = False,
    manager: bool = False,
    today: Optional[str] = None,
    tz: str = "Europe/Madrid",
    team: Optional[dict] = None,
) -> str:
    """WhatsApp gets the short seller persona and skills; the web assistant gets its own prompt.
    `manager` is the actor's team-reading right (role or visibility), decided by the server."""
    if web:
        return _web_prompt(artifacts, manager, today, tz, team)
    lines = [SOUL.strip()]
    if data_tools:
        lines += ["", DATA_PROMPT.strip()]
    lines += ["", "Session:", *_session_lines(artifacts)]
    lines.append("Skill index: " + ", ".join(sorted(SKILL_BODIES)))
    return "\n".join(lines)
