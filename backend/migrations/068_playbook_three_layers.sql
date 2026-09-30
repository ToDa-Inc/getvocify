-- Playbooks: the three-layer model (docs/superpowers/plans/2026-09-29-playbooks-v2.md, section 15).
--   1. playbook_versions.qualification: "what has to come out of the call", [{criterion_id, label,
--      why?, good?, bad?}] per version, edited in the draft and activated with the rest of it.
--      Publishing flips the draft's status in place (publish_playbook_version), so nothing copies
--      columns and nothing can drop it; save_playbook_draft (the legacy import path) inserts a
--      draft without it and takes the default.
--      Custom objections need no column: they are entries of playbook_versions.entries.
--   2. company_sales_knowledge: what Vocify knows about the company, once (ICP, personas, value
--      story, differentiators, cases, competitors, pricing, notes). One row per company, no draft:
--      a save takes effect at once. updated_at is bumped by a trigger so the API can answer
--      409 stale_knowledge to an editor that is not looking at the latest save.
-- Rollback: 068_playbook_three_layers.down.sql

BEGIN;

ALTER TABLE playbook_versions
  ADD COLUMN IF NOT EXISTS qualification JSONB NOT NULL DEFAULT '[]'::jsonb;

CREATE TABLE IF NOT EXISTS company_sales_knowledge (
  company_id UUID PRIMARY KEY,
  data JSONB NOT NULL DEFAULT '{}'::jsonb,
  source_id TEXT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION company_sales_knowledge_touch_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $touch$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$touch$;

DROP TRIGGER IF EXISTS company_sales_knowledge_updated_at ON company_sales_knowledge;
CREATE TRIGGER company_sales_knowledge_updated_at
  BEFORE UPDATE ON company_sales_knowledge
  FOR EACH ROW EXECUTE FUNCTION company_sales_knowledge_touch_updated_at();

COMMIT;
