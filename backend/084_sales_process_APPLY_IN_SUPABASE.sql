-- Sales process (run in the Supabase SQL editor). Same SQL as migrations/084_sales_process.sql.
--   company_sales_process       the company's own process: its types in order, and what each one is for (`stage`).
--   member_interaction_types    the types each member (or pending invitation) runs. NULL types = every type.
-- Service role only. The app does nothing different until SALES_PROCESS_ENABLED is on for the company.
-- NUMBER: 084 (081 demo_profiles, 082 live_assist_events_brain, 083 playbook_assistant): if someone else adds a 084, renumber this file.
-- Rollback: 084_sales_process.down.sql

BEGIN;

CREATE TABLE IF NOT EXISTS company_sales_process (
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  sales_motion_key TEXT NOT NULL,
  position INTEGER NOT NULL,
  stage TEXT NOT NULL CHECK (stage IN ('first_contact', 'deal')),
  PRIMARY KEY (company_id, sales_motion_key)
);

CREATE TABLE IF NOT EXISTS member_interaction_types (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  invitation_id UUID,
  types TEXT[],
  CHECK ((user_id IS NOT NULL) <> (invitation_id IS NOT NULL)),
  UNIQUE (company_id, user_id),
  UNIQUE (company_id, invitation_id)
);

ALTER TABLE company_sales_process ENABLE ROW LEVEL SECURITY;
ALTER TABLE member_interaction_types ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE
  t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['company_sales_process', 'member_interaction_types'] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
      EXECUTE format('REVOKE ALL ON %I FROM anon', t);
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
      EXECUTE format('REVOKE ALL ON %I FROM authenticated', t);
    END IF;
  END LOOP;
END $$;

COMMIT;
