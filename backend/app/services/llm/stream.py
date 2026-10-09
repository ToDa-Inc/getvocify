"""Assemble an OpenAI-style streaming chat completion into one assistant message."""

from __future__ import annotations

from typing import Optional


class ToolStreamAccumulator:
    """Feed parsed SSE chunks. Text deltas come back at once; tool calls assemble by index."""

    def __init__(self) -> None:
        self._text: list[str] = []
        self._calls: dict[int, dict] = {}
        self._reasoning: dict[tuple, dict] = {}
        self.usage: Optional[dict] = None
        self.model: Optional[str] = None

    def feed(self, chunk: dict) -> Optional[str]:
        if not isinstance(chunk, dict):
            return None
        if isinstance(chunk.get("usage"), dict):
            self.usage = chunk["usage"]
        if chunk.get("model"):
            self.model = chunk["model"]
        choices = chunk.get("choices") or []
        if not choices:
            return None
        delta = choices[0].get("delta") or {}
        for fragment in delta.get("tool_calls") or []:
            self._merge_call(fragment)
        for fragment in delta.get("reasoning_details") or []:
            self._merge_reasoning(fragment)
        text = delta.get("content")
        if isinstance(text, str) and text:
            self._text.append(text)
            return text
        return None

    def _merge_call(self, fragment: dict) -> None:
        index = fragment.get("index", len(self._calls))
        call = self._calls.setdefault(
            index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
        )
        if fragment.get("id"):
            call["id"] = fragment["id"]
        fn = fragment.get("function") or {}
        if fn.get("name"):
            call["function"]["name"] += fn["name"]
        if fn.get("arguments"):
            call["function"]["arguments"] += fn["arguments"]

    def _merge_reasoning(self, fragment: dict) -> None:
        """Reasoning arrives as text pieces per (type, index). Joined, they are what the provider must get back."""
        if not isinstance(fragment, dict):
            return
        key = (fragment.get("type"), fragment.get("index", 0))
        entry = self._reasoning.setdefault(key, {k: v for k, v in fragment.items() if k not in ("text", "summary", "data")})
        for field in ("text", "summary", "data"):
            if isinstance(fragment.get(field), str):
                entry[field] = entry.get(field, "") + fragment[field]

    def message(self) -> dict:
        calls = [self._calls[i] for i in sorted(self._calls)]
        message = {
            "role": "assistant",
            "content": "".join(self._text) if self._text else None,
            "tool_calls": calls or None,
        }
        if self._reasoning:
            message["reasoning_details"] = [self._reasoning[k] for k in sorted(self._reasoning, key=lambda k: (k[1], str(k[0])))]
        return message
