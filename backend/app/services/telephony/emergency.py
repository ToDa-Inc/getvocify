from __future__ import annotations

import re

_DIGITS = re.compile(r"\D+")

# National emergency / priority services we must never originate.
# Parking does not apply to 112/911; the browser From would leak.
_EMERGENCY_NATIONAL = frozenset(
    {
        "112",
        "911",
        "999",
        "000",
        "110",
        "119",
        "061",
        "062",
        "080",
        "091",
        "092",
        "016",
    }
)


def is_emergency_destination(raw: str) -> bool:
    digits = _DIGITS.sub("", raw or "")
    if not digits:
        return False
    if digits in _EMERGENCY_NATIONAL:
        return True
    # +34 112 / +1 911 after a country prefix
    for code in _EMERGENCY_NATIONAL:
        if digits.endswith(code) and len(digits) <= len(code) + 3:
            return True
    return False
