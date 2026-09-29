-- Removes the draft autosave timestamp. The API needs the column: roll back the deploy first.

BEGIN;

DROP TRIGGER IF EXISTS playbook_versions_updated_at ON playbook_versions;
DROP FUNCTION IF EXISTS playbook_versions_touch_updated_at();
ALTER TABLE playbook_versions DROP COLUMN IF EXISTS updated_at;

COMMIT;
