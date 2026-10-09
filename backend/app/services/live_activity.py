"""Which reps are transcribing a call live right now (or just were).

A Vocify call is transcribed live by the desktop app, which posts that transcript at hang-up and
makes the call's memo. Twilio's recording webhook arrives at the same moment; when the rep had a
live session, it gives the live transcript a moment to make the memo instead of transcribing the
audio again. Kept in this process: the live socket and the webhook are served by the same service.
"""

from __future__ import annotations

import time
from typing import Optional

# A session that ended this recently may still be posting its transcript.
RECENT_S = 90.0

_open: dict[str, int] = {}
_ended_at: dict[str, float] = {}


def session_started(user_id: Optional[str]) -> None:
    if user_id:
        _open[user_id] = _open.get(user_id, 0) + 1


def session_ended(user_id: Optional[str]) -> None:
    if not user_id:
        return
    left = _open.get(user_id, 0) - 1
    if left > 0:
        _open[user_id] = left
    else:
        _open.pop(user_id, None)
    _ended_at[user_id] = time.monotonic()


def recently_live(user_id: Optional[str], within_s: float = RECENT_S) -> bool:
    """True while the rep has a live session open, or had one end within `within_s`."""
    if not user_id:
        return False
    if _open.get(user_id, 0) > 0:
        return True
    ended = _ended_at.get(user_id)
    return ended is not None and time.monotonic() - ended <= within_s
