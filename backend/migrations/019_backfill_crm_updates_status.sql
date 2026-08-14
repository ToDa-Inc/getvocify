-- Migration 019: Backfill crm_updates.status for historical rows
--
-- Context: mark_success()/mark_failed()/mark_retrying() exist on
-- CRMUpdatesService but were never called from sync.py until now (they were
-- dead code). Every row ever written sits at the column default, 'pending',
-- regardless of what actually happened in HubSpot. Deduplication in sync.py
-- (note_already_created, tasks_already_synced) is about to start filtering
-- by status='success' instead of ignoring status entirely - without this
-- backfill, every historical memo would look "not yet synced" under the new
-- rule and a retry would create a duplicate note/tasks in the customer's
-- HubSpot timeline.
--
-- Backfill rule (verified against every create_update call site in sync.py
-- as of this migration, not assumed):
--   - create_note, create_tasks, merge_tasks, create_line_item, and the
--     deal-associated company patch (action_type upsert_company from step
--     4c) NEVER write a row when the HubSpot call fails - their except
--     blocks only log. So 100% of their historical rows are confirmed
--     successes.
--   - upsert_company (step 1), upsert_contact, and create_deal/update_deal
--     DO write a row on failure too, and always tag it with data.error. No
--     success-branch data dict for any action_type uses "error" as a key,
--     so presence of that key is an unambiguous, code-verified signal of
--     failure, not a guess.
--
-- Deployment ordering (see docs/DATABASE_SCHEMA.md "crm_updates backfill" for
-- the full writeup): this migration only fixes rows that already exist at
-- the moment it runs. It does NOT and CANNOT protect against an old
-- (pre-track()) code instance writing a *new* 'pending' row after this
-- migration commits during a rolling deploy - that row would carry
-- old-code semantics (pending == done, since the old code only ever wrote
-- after HubSpot confirmed) but look identical to a genuinely orphaned
-- track() pending row once the new dedupe/TTL logic is live. That gap is
-- closed in application code (CRMUpdatesService), not here, via a hardcoded
-- grandfather cutoff: status='success' OR (status='pending' AND
-- created_at < CRM_UPDATES_LEGACY_PENDING_CUTOFF). That cutoff must be set
-- to MAX(created_at) observed after this migration runs, plus a safety
-- margin covering the deploy's actual old/new overlap window - NOT invented
-- ahead of time. Run this migration, capture that MAX(created_at), THEN
-- implement track() with the cutoff hardcoded from that real value.
--
-- Idempotent: only touches rows still at the 'pending' default, so running
-- this twice (or after track() is already live and creating legitimate new
-- pending rows) is a no-op for anything already resolved.

BEGIN;

-- Failures: HubSpot itself rejected/errored the call. These already have
-- error_message-worthy detail sitting in data->>'error' from the except
-- block that wrote them; carry it into error_message so mark_failed()'s
-- column is populated the same way it would be going forward.
UPDATE crm_updates
SET status = 'failed',
    error_message = COALESCE(error_message, data->>'error'),
    completed_at = COALESCE(completed_at, created_at)
WHERE status = 'pending'
  AND data ? 'error';

-- Everything else at 'pending' was, by construction of the current
-- write-after-success code path, only ever written once HubSpot confirmed
-- the object existed.
UPDATE crm_updates
SET status = 'success',
    completed_at = COALESCE(completed_at, created_at)
WHERE status = 'pending'
  AND NOT (data ? 'error');

COMMIT;

-- Post-apply verification (run and paste results before considering this
-- migration done - "ran without error" is not "applied", per 018):
--
-- 1. No row should remain at the old default with no explanation:
--    SELECT status, COUNT(*) FROM crm_updates GROUP BY status;
--    Expect: no 'pending' rows at all right after this runs (until track()
--    starts legitimately creating new ones).
--
-- 2. Sanity check the split matches the pre-migration audit:
--    SELECT action_type, status, COUNT(*) FROM crm_updates
--    GROUP BY action_type, status ORDER BY action_type;
--
-- 3. Capture the real cutoff for the track() grandfather clause:
--    SELECT MAX(created_at) FROM crm_updates;
