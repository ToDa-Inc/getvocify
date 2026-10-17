-- Rollback of 084_sales_process.sql: loses the company's own process and the types assigned to members.
BEGIN;
DROP TABLE IF EXISTS member_interaction_types;
DROP TABLE IF EXISTS company_sales_process;
COMMIT;
