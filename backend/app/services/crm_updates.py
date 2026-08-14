"""
CRM Updates service for tracking what was pushed to CRM.

RLS note (FASE 2.2, point 3): crm_updates only has a SELECT policy ("Users
can view own crm updates" - see docs/DATABASE_SCHEMA.md). INSERT/UPDATE from
this service have no policy allowing them at all, so they only work because
every caller constructs this service with the service_role Supabase client
from app.deps.get_supabase() (which pins the Authorization header back to
service_role on every call via _ensure_service_role_auth, specifically
because supabase-py can otherwise swap it to a user JWT after a SIGNED_IN
event - see the comment there). service_role bypasses RLS entirely, so
track()/create_update()/mark_*() never hit the missing INSERT/UPDATE
policies today. If this service is ever constructed with a
non-service_role client (e.g. a future per-request user-scoped client), every
write here will fail with 42501 and dedupe will silently degenerate back to
"nothing is ever marked done" - the exact bug this file fixes. There is no
code-level guard against that here; the guard is "always construct this via
get_supabase()", so verify that at the call site if this Ever changes.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Dict, Optional, Sequence

from supabase import Client


# TTL for orphaned 'pending' rows (reserved by track() but never confirmed -
# process died between reserve and the HubSpot call returning, or while
# handling its result). Justified against the real HubSpot HTTP client
# timeout, not a round number: HubSpotClient.DEFAULT_TIMEOUT is 30s per
# request (backend/app/services/hubspot/client.py). The most call-heavy
# single tracked action is note creation's fallback path (combined
# create+associate POST, then on specific 400/403/404 errors a bare create
# POST plus up to 3 separate association calls for deal+contact+company) -
# at most 4 sequential HubSpot calls, so 4 x 30s = 120s (2 minutes) is the
# worst-case legitimate duration for any single track()'d unit. 10 minutes
# is 5x that, comfortably absorbing scheduling/GC jitter and connection-pool
# delays without mistaking a genuinely slow-but-alive request for abandoned.
CRM_UPDATES_PENDING_TTL_MINUTES = 10

# Grandfather cutoff for the pending -> success/failed transition (FASE 2.2,
# point 1 in the design discussion - see docs/DATABASE_SCHEMA.md and
# migrations/019_backfill_crm_updates_status.sql). Every row written before
# track() existed only ever got a 'pending' row created AFTER HubSpot had
# already confirmed success (or, for 3 action types, after a confirmed
# failure) - "pending" under that old code meant "done", never "in flight".
# Migration 019 resolves every row that existed at the moment it ran into
# 'success'/'failed', but cannot protect against an old-code instance still
# running during a rolling deploy and inserting a NEW 'pending' row after
# the migration committed - that row would carry old-code semantics but be
# indistinguishable in shape from a genuine track() reservation. TTL alone
# cannot resolve that ambiguity (age doesn't encode which code wrote a row),
# so any 'pending' row older than this cutoff is trusted as done outright,
# permanently, regardless of TTL.
#
# Real value, not invented ahead of time: migration 019 was applied on
# 2026-08-14; `SELECT MAX(created_at) FROM crm_updates;` immediately after
# returned 2026-08-11 21:37:56.359864+00 (a memo created before the backfill
# ran, not a race with the deploy itself - the backfill only touches
# existing rows, it doesn't create new ones). +30 minutes safety margin,
# covering Railway's old/new container overlap during the track()-enabling
# deploy (health-check cutover is minutes, not hours) -> the value below.
# Must stay timezone-aware (UTC) - comparing against a naive datetime raises
# TypeError in is_action_already_done.
#
# Startup validation (app.main's startup_event) fails the app's boot
# entirely if this is ever None - see the "WHERE this fires" note on
# is_action_already_done below for why that matters.
#
# TODO(remove after 2026-09-15): once this date has passed, no legitimate
# 'pending' row can predate the cutoff anymore (anything track() itself
# created and abandoned since deploy will already have been resolved by the
# TTL check above), so this constant and every branch that reads it become
# dead weight - delete them.
CRM_UPDATES_LEGACY_PENDING_CUTOFF: Optional[datetime] = datetime(2026, 8, 11, 22, 8, 0, tzinfo=timezone.utc)

DONE_ACTION_STATUSES = ("success",)


class TrackedUpdate:
    """
    Mutable handle yielded by CRMUpdatesService.track(). The caller fills in
    `data` (and optionally `resource_id`/`response`) with whatever the
    HubSpot call actually returned, before the `async with` block exits
    normally - that's what gets written on mark_success().
    """

    def __init__(self, update_id: str) -> None:
        self.update_id = update_id
        self.data: Dict[str, Any] = {}
        self.resource_id: Optional[str] = None
        self.response: Optional[Dict[str, Any]] = None


class CRMUpdatesService:
    """Service for creating and tracking CRM updates"""

    def __init__(self, supabase: Client):
        self.supabase = supabase

    async def create_update(
        self,
        memo_id: str,
        user_id: str,
        crm_connection_id: str,
        action_type: str,
        resource_type: str,
        data: Dict[str, Any]
    ) -> str:
        """
        Create a CRM update record, status defaults to 'pending'.

        Kept as a standalone method (not folded into track()) because
        merge_tasks still calls this directly - its granularity is per
        sub-operation (create/update/delete several tasks in one pass), and
        a single track() call can't represent that. See the merge_tasks call
        site in sync.py for the explicit note on why it's excluded.

        Returns:
            The created CRM update ID
        """
        update_data = {
            "memo_id": memo_id,
            "user_id": user_id,
            "crm_connection_id": crm_connection_id,
            "action_type": action_type,
            "resource_type": resource_type,
            "data": data,
            "status": "pending",
        }

        result = self.supabase.table("crm_updates").insert(update_data).execute()

        if not result.data:
            raise Exception("Failed to create CRM update record")

        return result.data[0]["id"]

    @asynccontextmanager
    async def track(
        self,
        *,
        memo_id: str,
        user_id: str,
        crm_connection_id: str,
        action_type: str,
        resource_type: str,
    ) -> AsyncIterator[TrackedUpdate]:
        """
        Reserve -> execute -> confirm.

        Writes a 'pending' row BEFORE the caller's HubSpot call runs, so a
        crash mid-call (process killed, OOM, hard timeout - anything that
        never reaches the caller's own except block) still leaves a row
        behind for the TTL check to eventually surface, instead of the
        historical pattern of writing nothing at all until after the call
        returns. That's what makes "something created in HubSpot with zero
        crm_updates row" structurally impossible going forward, rather than
        merely detectable after the fact via logs.

        Usage:
            async with self.crm_updates.track(
                memo_id=str(memo_id), user_id=user_id,
                crm_connection_id=str(connection_id),
                action_type="upsert_company", resource_type="company",
            ) as tracked:
                company = await self.companies.create_or_update(...)
                if company:
                    company_id = company.id
                    tracked.data = {"company_id": company_id, "name": extraction.companyName}
                    tracked.resource_id = company_id

        On a clean exit, marks the row 'success' with whatever `tracked.data`
        /`resource_id`/`response` the caller set (an empty `data` is valid -
        e.g. a branch that legitimately did nothing). On any exception,
        marks it 'failed' with str(exception) and RE-RAISES - callers keep
        their existing try/except around the `async with` block for their
        own control flow (result.error, logging, fallbacks) unchanged; this
        only replaces the manual "write a row in both branches" bookkeeping.
        """
        update_id = await self.create_update(
            memo_id=memo_id,
            user_id=user_id,
            crm_connection_id=crm_connection_id,
            action_type=action_type,
            resource_type=resource_type,
            data={},
        )
        tracked = TrackedUpdate(update_id)
        try:
            yield tracked
        except Exception as e:
            await self.mark_failed(update_id, error_message=str(e))
            raise
        else:
            await self.mark_success(
                update_id,
                data=tracked.data,
                resource_id=tracked.resource_id,
                response=tracked.response,
            )

    async def mark_success(
        self,
        update_id: str,
        data: Optional[Dict[str, Any]] = None,
        resource_id: Optional[str] = None,
        response: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Mark a CRM update as successful.

        `data` is settable here (not just at create_update() time) because
        track() reserves the row before the HubSpot call, when the actual
        result (company_id, note_id, etc.) isn't known yet - it's only
        filled in once the call returns, at confirm time.
        """
        update_data: Dict[str, Any] = {
            "status": "success",
            "completed_at": datetime.utcnow().isoformat(),
        }
        if data is not None:
            update_data["data"] = data
        if resource_id is not None:
            update_data["resource_id"] = resource_id
        if response is not None:
            update_data["response"] = response
        self.supabase.table("crm_updates").update(update_data).eq("id", update_id).execute()

    async def mark_failed(
        self,
        update_id: str,
        error_message: str,
        retry_count: Optional[int] = None
    ) -> None:
        """Mark a CRM update as failed"""
        update_data = {
            "status": "failed",
            "error_message": error_message,
            "completed_at": datetime.utcnow().isoformat(),
        }

        if retry_count is not None:
            update_data["retry_count"] = retry_count

        self.supabase.table("crm_updates").update(update_data).eq("id", update_id).execute()

    async def mark_retrying(
        self,
        update_id: str,
        retry_count: int
    ) -> None:
        """Mark a CRM update as retrying"""
        self.supabase.table("crm_updates").update({
            "status": "retrying",
            "retry_count": retry_count,
        }).eq("id", update_id).execute()

    async def get_memo_updates(self, memo_id: str) -> list[Dict[str, Any]]:
        """Get all CRM updates for a memo"""
        result = self.supabase.table("crm_updates").select("*").eq("memo_id", memo_id).order("created_at", desc=False).execute()
        return result.data or []

    @staticmethod
    def is_action_already_done(
        previous_updates: Sequence[Dict[str, Any]],
        action_types: Sequence[str],
    ) -> bool:
        """
        True if any row for one of `action_types` already completed for this
        memo, under the semantics track() writes going forward:
          - status='success' always counts as done.
          - status='failed' or 'retrying' never counts - a failure must be
            retryable, not silently treated as "already handled".
          - status='pending' counts ONLY if it predates
            CRM_UPDATES_LEGACY_PENDING_CUTOFF (see that constant) - i.e. it
            was written by the pre-track() code, where a pending row always
            meant success. A 'pending' row created after the cutoff is a
            real track() reservation: if it's still pending, the TTL check
            (count_stale_pending), not this function, is what surfaces it as
            abandoned. This function never treats a post-cutover pending row
            as done, on purpose - duplicating a note is worse than skipping
            one retry.

        WHERE this fires if the cutoff is missing: this is called from
        inside sync_memo (note_already_created, tasks_already_synced), on
        the request path, for whatever specific memo is being synced right
        now. Raising here mid-request would mean a real user's /approve call
        gets a 500 the first time their memo happens to have an old-style
        legacy pending row - a landmine, not a safety net. That's why
        app.main's startup_event ALSO validates
        CRM_UPDATES_LEGACY_PENDING_CUTOFF unconditionally, before the app
        accepts any traffic: a misconfigured cutoff should fail the deploy
        at boot (visible in Railway's deploy logs, nobody's memo affected),
        not fail one unlucky sync in production. The RuntimeError here is
        deliberately kept anyway, as defense-in-depth for any code path that
        constructs CRMUpdatesService without going through the FastAPI app
        (scripts, workers, tests) and therefore never runs that startup
        check - it should never be the FIRST line of defense.
        """
        action_set = set(action_types)
        for update in previous_updates:
            if update.get("action_type") not in action_set:
                continue
            status = update.get("status")
            if status in DONE_ACTION_STATUSES:
                return True
            if status == "pending":
                if CRM_UPDATES_LEGACY_PENDING_CUTOFF is None:
                    raise RuntimeError(
                        "CRM_UPDATES_LEGACY_PENDING_CUTOFF is unset (see "
                        "app/services/crm_updates.py) - a 'pending' "
                        f"{update.get('action_type')} row exists for this "
                        "memo and cannot be classified as done-or-not "
                        "without it. Set the cutoff to the real "
                        "MAX(created_at) from migration 019 before "
                        "deploying this code against a database that has "
                        "pre-track() rows."
                    )
                created_at = _parse_timestamp(update.get("created_at"))
                if created_at is not None and created_at < CRM_UPDATES_LEGACY_PENDING_CUTOFF:
                    return True
        return False

    async def count_stale_pending(
        self, ttl_minutes: int = CRM_UPDATES_PENDING_TTL_MINUTES
    ) -> int:
        """
        Count 'pending' rows older than the TTL - orphaned reservations
        whose HubSpot call never confirmed either way. This is a monitoring
        signal (see the stale-pending gauge in app.metrics), not a dedupe
        decision: a row this old is NOT treated as "done" by
        is_action_already_done regardless of this count, and a retry of its
        memo is free to try again once past the grandfather-cutoff logic
        above. Also doubles as a sanity check on migration 019 itself - a
        large count right after deploying track() means either the backfill
        didn't run, or didn't run before track()-enabled code went live.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=ttl_minutes)).isoformat()
        result = (
            self.supabase.table("crm_updates")
            .select("id", count="exact")
            .eq("status", "pending")
            .lt("created_at", cutoff)
            .execute()
        )
        return result.count or 0


def validate_startup_config() -> None:
    """
    Fail the app's boot, not a random user's /approve request, if this
    module is misconfigured. Call from app.main's startup_event, before the
    app is marked ready for traffic - see the "WHERE this fires" note on
    CRMUpdatesService.is_action_already_done for why the ordering matters.
    """
    if CRM_UPDATES_LEGACY_PENDING_CUTOFF is None:
        raise RuntimeError(
            "CRM_UPDATES_LEGACY_PENDING_CUTOFF is unset in "
            "app/services/crm_updates.py - set it to the real "
            "MAX(created_at) from migration 019 (plus a safety margin) "
            "before this app can serve traffic. Refusing to start."
        )


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
