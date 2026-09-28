-- Lista 4 (T4, E11): when Vocify creates a deal in the CRM for a contact that has none.
--   crm_configurations.deal_creation_rule, chosen by the Head of Sales in Ajustes -> CRM:
--     always               today's behaviour (default): approving a call may create the deal;
--     meeting_booked       only when the rep marks the call "Reunión agendada";
--     follow_up_or_meeting also when the rep marks it "Seguimiento";
--     never                Vocify never creates deals, it only updates the contact.
--   A deal that already exists is always updated. The backend applies the rule on approve
--   (skip_deal), not only the UI - only with AFTER_CALL_FLOW_ENABLED on for the company.
-- Rollback: 063_deal_creation_rule.down.sql

BEGIN;

ALTER TABLE crm_configurations
  ADD COLUMN IF NOT EXISTS deal_creation_rule TEXT NOT NULL DEFAULT 'always';

ALTER TABLE crm_configurations
  DROP CONSTRAINT IF EXISTS crm_configurations_deal_creation_rule_check;

ALTER TABLE crm_configurations
  ADD CONSTRAINT crm_configurations_deal_creation_rule_check
  CHECK (deal_creation_rule IN ('always', 'meeting_booked', 'follow_up_or_meeting', 'never'));

COMMIT;
