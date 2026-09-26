-- Memos were inserted without company_id, so every company-scoped read (briefs, priorities,
-- team insights) found nothing. company_id stays immutable once set; only NULL may be filled.
-- Rollback: 050_memos_company_backfill.down.sql

BEGIN;

CREATE OR REPLACE FUNCTION memos_lock_capture_identity()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'UPDATE' THEN
    IF OLD.company_id IS NOT NULL AND NEW.company_id IS DISTINCT FROM OLD.company_id THEN
      RAISE EXCEPTION 'memos.company_id is immutable';
    END IF;
    IF OLD.client_capture_id IS NOT NULL
       AND NEW.client_capture_id IS DISTINCT FROM OLD.client_capture_id THEN
      RAISE EXCEPTION 'memos.client_capture_id is immutable';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

UPDATE memos AS m
SET company_id = cm.company_id
FROM company_members AS cm
WHERE m.company_id IS NULL
  AND cm.user_id = m.user_id;

COMMIT;
