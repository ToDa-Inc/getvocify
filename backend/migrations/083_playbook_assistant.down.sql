-- Drops the playbook assistant's tables (sessions, improvement queue, suggestion verdicts).

BEGIN;

DROP TABLE IF EXISTS playbook_suggestion_outcomes;
DROP TABLE IF EXISTS playbook_review_moments;
DROP TABLE IF EXISTS playbook_assistant_sessions;

COMMIT;
