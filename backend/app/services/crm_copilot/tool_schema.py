"""OpenAI-style function definitions, shared by the Ask tool modules."""

from __future__ import annotations

from typing import Any, Optional


def fn(name: str, description: str, properties: dict, required: Optional[list] = None) -> dict:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return {"type": "function", "function": {"name": name, "description": description, "parameters": schema}}
