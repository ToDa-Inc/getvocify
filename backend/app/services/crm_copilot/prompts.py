from __future__ import annotations

from pathlib import Path

_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _DIR / "skills"

SOUL = (_DIR / "soul.md").read_text()
SKILL_BODIES = {
    path.stem: path.read_text()
    for path in sorted(_SKILL_DIR.glob("*.md"))
}


def build_system_prompt(artifacts: dict) -> str:
    copilot = (artifacts or {}).get("copilot") or {}
    memory = copilot.get("memory") or []
    lines = [SOUL.strip(), "", "Session:"]
    for key in (
        "last_contact_id",
        "last_company_id",
        "last_deal_id",
        "last_contact_url",
        "last_deal_url",
        "memo_id",
    ):
        val = copilot.get(key)
        if val:
            lines.append(f"- {key}: {val}")
    if memory:
        lines.append("Memory:")
        for item in memory[-12:]:
            lines.append(f"- {item}")
    lines.append("Skill index: " + ", ".join(sorted(SKILL_BODIES)))
    return "\n".join(lines)
