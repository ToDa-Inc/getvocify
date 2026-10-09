"""T9: Head of Sales onboarding wizard (`ONBOARDING_WIZARD_ENABLED`).

Pure "which step is next" logic, kept apart from CompanyService's Supabase reads so it can
be tested with a plain dict. Every step can be skipped from the UI; `state` just needs to
carry True for a step once it is either genuinely done or the person chose to skip it.
"""

from __future__ import annotations

from typing import Mapping, Optional

# Order matters: this is the order the wizard walks the person through.
#   crm       -> D-less: connect (or confirm) the CRM
#   team      -> invite teammates with their commercial type (SDR/AE/General)
#   handoff   -> SDR->AE routing (D2)
#   playbooks -> link to the playbook editor (T2)
#   strategy  -> the Head of Sales's sales strategy (D10)
STEPS: tuple[str, ...] = ("crm", "team", "handoff", "playbooks", "strategy")


def next_onboarding_step(state: Mapping[str, bool]) -> Optional[str]:
    """The first step in STEPS not yet marked done/skipped in `state`, or None once every
    step is. A step missing from `state` counts as pending, same as an explicit False."""
    for step in STEPS:
        if not state.get(step):
            return step
    return None
