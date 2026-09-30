"""A small evaluator for PostgREST `or=(...)` expressions, so tests can run the filter a route sends."""

from __future__ import annotations

from typing import Any


def _split(expression: str) -> list[str]:
    parts, depth, current = [], 0, ""
    for char in expression:
        if char == "," and depth == 0:
            parts.append(current)
            current = ""
            continue
        depth += {"(": 1, ")": -1}.get(char, 0)
        current += char
    return [*parts, current]


def matches(expression: str, row: dict[str, Any]) -> bool:
    """SQL semantics for the operators the app uses: a comparison against NULL is never true."""
    return any(_term(term, row) for term in _split(expression))


def _term(term: str, row: dict[str, Any]) -> bool:
    if term.startswith("and(") and term.endswith(")"):
        return all(_term(part, row) for part in _split(term[4:-1]))
    if term.startswith("or(") and term.endswith(")"):
        return matches(term[3:-1], row)
    column, op, value = term.split(".", 2)
    current = row.get(column)
    if op == "is":
        return value == "null" and current is None
    if current is None:
        return False
    if op == "eq":
        return current == value
    if op == "in":
        return current in value[1:-1].split(",")
    if op == "not" and value.startswith("in."):
        return current not in value[4:-1].split(",")
    raise ValueError(f"unsupported clause: {term}")
