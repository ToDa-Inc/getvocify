-- Restores the strict trigger. Backfilled company_id values stay: they are the author's real
-- workspace, and clearing them would break company-scoped reads again.

BEGIN;

CREATE OR REPLACE FUNCTION memos_lock_capture_identity()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'UPDATE' THEN
    IF NEW.company_id IS DISTINCT FROM OLD.company_id THEN
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

COMMIT;
