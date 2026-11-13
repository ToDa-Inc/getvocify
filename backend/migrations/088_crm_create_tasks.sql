-- crm_configurations.create_tasks: whether Vocify proposes tasks from a call and writes them to the CRM. Set by the
-- admin in Ajustes -> CRM («Tasks» under «What Vocify creates»). Off: the review and the island propose none and the
-- sync writes none; a task the rep adds by hand is still written.
-- Default true, so every existing company keeps today's behaviour. The backend reads it with .get(..., True) and writes
-- it only when the client sends it, so the app works the same until this is applied (turning the switch off then says
-- it could not save).
-- NUMBER: 088 (087 playbook_conduct): if someone else adds a 088, renumber this file.
-- Rollback: 088_crm_create_tasks.down.sql

BEGIN;

ALTER TABLE crm_configurations ADD COLUMN IF NOT EXISTS create_tasks BOOLEAN NOT NULL DEFAULT TRUE;

COMMIT;
