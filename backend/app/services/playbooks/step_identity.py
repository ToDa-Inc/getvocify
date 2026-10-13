"""Which step of the published playbook a stored step verdict counts for. No I/O.

A verdict was judged against one criterion. When the playbook is republished, a step whose
criterion did not change keeps its history even if its label or step_id changed. A step whose
criterion changed starts from zero: the old verdicts stay in the call's history, they just stop
counting. Old calls are never read again against the new steps. Verdicts stored without their
criterion fall back to the step_id."""

from __future__ import annotations

from typing import Iterable


def criterion_key(text) -> str:
    """Case, spacing and a closing full stop do not make a different criterion."""
    return " ".join(str(text or "").casefold().split()).rstrip(" .;:")


class StepMatcher:
    def __init__(self, steps: Iterable[dict]):
        self._criterion_of: dict[str, str] = {}
        self._by_criterion: dict[str, str] = {}
        for step in steps or []:
            if not isinstance(step, dict) or not step.get("step_id"):
                continue
            step_id = str(step["step_id"])
            key = criterion_key(step.get("criterion"))
            self._criterion_of.setdefault(step_id, key)
            if key:
                self._by_criterion.setdefault(key, step_id)

    def match(self, step_id, criterion=None) -> str | None:
        """The published step_id this verdict counts for, or None when it counts for none."""
        step_id = str(step_id or "")
        key = criterion_key(criterion)
        live_key = self._criterion_of.get(step_id)
        if live_key is not None and (not key or not live_key or live_key == key):
            return step_id
        return self._by_criterion.get(key) if key else None
