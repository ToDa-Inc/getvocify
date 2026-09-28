"""Input revision for intelligence. Content hash, not updated_at."""

from __future__ import annotations

import hashlib
import json
from typing import Optional


def input_revision(
    *,
    schema: str,
    extraction_revision: str,
    notes_revision: Optional[str],
    identity: str,
    playbook_version_id: Optional[str] = None,
) -> str:
    payload = {
        "schema": schema,
        "extraction": extraction_revision,
        "notes": notes_revision,
        "identity": identity,
        "playbook_version_id": playbook_version_id,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
