-- Playbook draft autosave. The editor now saves the draft in place instead of inserting one
-- playbook_versions row per save, and compares updated_at to notice that someone else changed
-- the draft (409 stale_draft). Existing rows start with updated_at = created_at.
-- Rollback: 066_playbook_draft_autosave.down.sql

BEGIN;

ALTER TABLE playbook_versions
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- Before the trigger exists, so the backfill does not stamp every row with "now".
UPDATE playbook_versions SET updated_at = created_at;

CREATE OR REPLACE FUNCTION playbook_versions_touch_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $touch$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$touch$;

DROP TRIGGER IF EXISTS playbook_versions_updated_at ON playbook_versions;
CREATE TRIGGER playbook_versions_updated_at
  BEFORE UPDATE ON playbook_versions
  FOR EACH ROW EXECUTE FUNCTION playbook_versions_touch_updated_at();

COMMIT;
