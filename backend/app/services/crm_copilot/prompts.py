from __future__ import annotations

from pathlib import Path

_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _DIR / "skills"
_PROMPTS_DIR = _DIR.parents[1] / "prompts"

SOUL = (_DIR / "soul.md").read_text()
DATA_PROMPT_VERSION = "ask_vocify_data_v1"
DATA_PROMPT = (_PROMPTS_DIR / f"{DATA_PROMPT_VERSION}.md").read_text(encoding="utf-8")
SKILL_BODIES = {
    path.stem: path.read_text()
    for path in sorted(_SKILL_DIR.glob("*.md"))
}


def with_data_prompt(system: str) -> str:
    data = DATA_PROMPT.strip()
    if data in system:
        return system
    soul = SOUL.strip()
    if system.startswith(soul):
        return f"{soul}\n\n{data}{system[len(soul):]}"
    return f"{system}\n\n{data}"


def build_system_prompt(artifacts: dict, *, data_tools: bool = False) -> str:
    copilot = (artifacts or {}).get("copilot") or {}
    memory = copilot.get("memory") or []
    lines = [SOUL.strip()]
    if data_tools:
        lines += ["", DATA_PROMPT.strip()]
    lines += ["", "Session:"]
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
