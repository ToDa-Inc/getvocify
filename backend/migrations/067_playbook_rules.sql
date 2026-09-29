-- Playbooks v2 (fase 2, T7): a label for the type and the rule that says which calls it applies to.
-- applies_to = {role: sdr|ae|any, channels: [call|meeting|visit], contact: new|contacted|inbound|any,
-- deal_stages: [crm stage id, ...]}. NULL on a catalog type means "the catalog's default rule".
-- Rollback: 067_playbook_rules.down.sql

BEGIN;

ALTER TABLE playbooks
  ADD COLUMN IF NOT EXISTS label TEXT,
  ADD COLUMN IF NOT EXISTS applies_to JSONB;

COMMIT;
