-- Removes the qualification criteria and the company knowledge. The API needs both: roll back the
-- deploy first. This deletes the data in them.

BEGIN;

DROP TRIGGER IF EXISTS company_sales_knowledge_updated_at ON company_sales_knowledge;
DROP FUNCTION IF EXISTS company_sales_knowledge_touch_updated_at();
DROP TABLE IF EXISTS company_sales_knowledge;
ALTER TABLE playbook_versions DROP COLUMN IF EXISTS qualification;

COMMIT;
