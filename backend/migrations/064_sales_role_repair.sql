-- 064: restore the sales_role contract from 054_sales_roles.sql.
--
-- A draft migration from another branch (037_sales_roles.sql, never merged) was run by
-- hand on at least one database. It could leave company_members.sales_role with:
--   * a CHECK of ('sdr','ae','manager','other') instead of 054's
--     (NULL or 'sdr','ae','general') -> assigning "General" fails with 23514;
--   * NOT NULL DEFAULT 'other' when it ran before 054 -> 054 itself then fails.
-- This puts the column back to exactly what 054 defines. NULL already means "general"
-- (054), so 'other'/'manager' rows become NULL.
--
-- Idempotent: on a database that never ran the draft it changes nothing.
-- Leftover columns from the draft (company_members.started_on, companies.sales_settings)
-- are unused and harmless; they are not dropped here.
-- Rollback: 064_sales_role_repair.down.sql (no-op by design).

BEGIN;

ALTER TABLE company_members ADD COLUMN IF NOT EXISTS sales_role TEXT;
ALTER TABLE company_members ALTER COLUMN sales_role DROP NOT NULL;
ALTER TABLE company_members ALTER COLUMN sales_role DROP DEFAULT;

ALTER TABLE company_members
  DROP CONSTRAINT IF EXISTS company_members_sales_role_check;

-- The draft may have left its CHECK under another name (or an auto-generated one):
-- drop every remaining CHECK on company_members that references sales_role, otherwise
-- it keeps rejecting 'general' after the 054 constraint is back.
DO $$
DECLARE
  c RECORD;
BEGIN
  FOR c IN
    SELECT conname
    FROM pg_constraint
    WHERE conrelid = 'company_members'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) ILIKE '%sales_role%'
  LOOP
    EXECUTE format('ALTER TABLE company_members DROP CONSTRAINT %I', c.conname);
  END LOOP;
END $$;

UPDATE company_members
  SET sales_role = NULL
  WHERE sales_role IS NOT NULL AND sales_role NOT IN ('sdr', 'ae', 'general');

ALTER TABLE company_members
  ADD CONSTRAINT company_members_sales_role_check
  CHECK (sales_role IS NULL OR sales_role IN ('sdr', 'ae', 'general'));

COMMIT;
