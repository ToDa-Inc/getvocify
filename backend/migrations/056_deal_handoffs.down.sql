-- Rollback for 056_deal_handoffs.sql

BEGIN;

DROP TABLE IF EXISTS deal_handoffs;

COMMIT;
