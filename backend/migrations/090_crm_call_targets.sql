-- crm_configurations.call_targets: which CRM records a call is saved on (its note, its call activity and its tasks):
-- any of 'deal', 'company', 'contact'. Set by the admin in Ajustes -> CRM («Save the call on»). Without 'deal' Vocify
-- neither updates nor creates deals from calls. A call with none of the chosen records goes on whichever it has.
BEGIN;

ALTER TABLE crm_configurations
  ADD COLUMN IF NOT EXISTS call_targets TEXT[] NOT NULL DEFAULT ARRAY['deal', 'company', 'contact']::TEXT[];

ALTER TABLE crm_configurations DROP CONSTRAINT IF EXISTS crm_configurations_call_targets_check;
ALTER TABLE crm_configurations ADD CONSTRAINT crm_configurations_call_targets_check
  CHECK (cardinality(call_targets) > 0 AND call_targets <@ ARRAY['deal', 'company', 'contact']::TEXT[]);

COMMIT;
