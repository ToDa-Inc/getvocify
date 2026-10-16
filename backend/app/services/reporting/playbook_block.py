"""The playbook answers that keep failing, as a block of the Head of Sales' weekly report.

Optional and isolated: the block exists only when the assistant and the success rate are both switched on and at least one
answer failed three times in the last month; anything that goes wrong reading it leaves the report as it always was. The
link takes the reader to the screen where those answers are fixed.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime
from typing import Any, Optional

from app.services.feature_flags import is_enabled
from app.services.playbooks.assistant_store import AssistantStore, get_assistant_store
from app.services.playbooks.catalog import catalog_label
from app.services.playbooks.repository import PlaybookRepository, get_playbook_repository
from app.services.playbooks.review_queue import answer_of, failing_by_answer, recent_outcomes
from app.services.reporting.presentation import OBJECTION_LABELS_ES

logger = logging.getLogger(__name__)

LINK = "/dashboard/playbook?view=improve"
FLAGS = ("PLAYBOOK_ASSISTANT_ENABLED", "PLAYBOOK_SUCCESS_RATE_ENABLED")


def _name(group: dict, repository: Optional[PlaybookRepository], company_id: str) -> str:
    key = str(group["answer_key"])
    if key.startswith("objection:custom:"):
        found = answer_of(repository, company_id, group.get("sales_motion_key") or "discovery", key) if repository else None
        return str((found or {}).get("label") or "").strip() or key.split(":", 2)[2].replace("-", " ").capitalize()
    category = key.split(":", 1)[-1]
    return OBJECTION_LABELS_ES.get(category, category)


def playbook_improvement_block(
    store: AssistantStore, company_id: str, *, limit: int = 5, repository: Optional[PlaybookRepository] = None, now: Optional[datetime] = None,
) -> Optional[dict]:
    """{items: [{label, failing, total}], link} for the `limit` answers that failed most, or None when none failed three times
    or more in the last month. `failing` counts the suggestions nobody said or that did not settle it, out of `total` judged.
    The same answer in two call types is told apart by the type's name."""
    groups = failing_by_answer(recent_outcomes(store, company_id, now=now, after_fixes=True), now=now)[:limit]
    if not groups:
        return None
    names = [_name(group, repository, company_id) for group in groups]
    repeated = {name for name, count in Counter(names).items() if count > 1}
    items = []
    for group, name in zip(groups, names):
        motion = group.get("sales_motion_key") or ""
        label = f"{name} · {catalog_label(motion, 'es') or motion}" if name in repeated and motion else name
        items.append({"label": label, "failing": group["failing"], "total": group["total"]})
    return {"items": items, "link": LINK}


def playbook_improvement_for(supabase: Any, company_id: str, *, now: Optional[datetime] = None) -> Optional[dict]:
    """The block for a company's weekly report, or None: flags off, tables not there yet, nothing failing or any error."""
    if not all(is_enabled(supabase, company_id, flag) for flag in FLAGS):
        return None
    try:
        return playbook_improvement_block(get_assistant_store(supabase), company_id, repository=get_playbook_repository(), now=now)
    except Exception as exc:
        logger.warning("playbook improvements left out of the weekly report: %s", type(exc).__name__)
        return None
