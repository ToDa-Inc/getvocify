-- Drops the deal creation rule and its check.

BEGIN;

ALTER TABLE crm_configurations
  DROP CONSTRAINT IF EXISTS crm_configurations_deal_creation_rule_check;

ALTER TABLE crm_configurations
  DROP COLUMN IF EXISTS deal_creation_rule;

COMMIT;
