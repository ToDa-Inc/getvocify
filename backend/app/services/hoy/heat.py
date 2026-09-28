"""T5: heat_score, a pure second-order signal used to order cards inside the same Hoy tier.

Facts a caller does not have are simply omitted - an unknown fact never guesses at a
score, it just contributes nothing (D-consistent with the rest of Hoy: unknown interest
stays unknown). Weighing is intentionally coarse; this is a tiebreaker, not the tier
itself.
"""

from __future__ import annotations

_INTEREST_WEIGHT = {"high": 40, "medium": 20, "low": 5, "none": 0}
_PAIN_WEIGHT = 20
_OBJECTION_WEIGHT = 10
_EMAIL_REPLY_WEIGHT = 10
_RECENCY_MAX = 20
_RECENCY_HALF_LIFE_DAYS = 10


def heat_score(facts: dict) -> int:
    """0-100, higher = hotter. Pure; no I/O, no clock reads."""
    score = 0.0
    interest = facts.get("interest")
    if interest in _INTEREST_WEIGHT:
        score += _INTEREST_WEIGHT[interest]
    if facts.get("pain_confirmed"):
        score += _PAIN_WEIGHT
    if facts.get("objection_open"):
        score += _OBJECTION_WEIGHT
    if facts.get("email_replied"):
        score += _EMAIL_REPLY_WEIGHT
    days_silent = facts.get("days_silent")
    if isinstance(days_silent, (int, float)) and days_silent >= 0:
        # Decays toward 0 as silence grows; a same-day touch scores the full weight.
        score += _RECENCY_MAX * (_RECENCY_HALF_LIFE_DAYS / (_RECENCY_HALF_LIFE_DAYS + days_silent))
    return max(0, min(100, round(score)))
