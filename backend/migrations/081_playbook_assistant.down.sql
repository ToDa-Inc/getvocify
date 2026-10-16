-- Drops the playbook assistant's tables (sessions, model calls, improvement queue, suggestion verdicts).

BEGIN;

DROP TABLE IF EXISTS playbook_suggestion_outcomes;
DROP TABLE IF EXISTS playbook_review_moments;
DROP TABLE IF EXISTS playbook_model_calls;
DROP TABLE IF EXISTS playbook_assistant_sessions;

COMMIT;
