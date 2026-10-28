-- Drops «Cómo trabajamos» with its column; the live brain goes back to the goal fixed in code.

BEGIN;

ALTER TABLE playbooks DROP COLUMN IF EXISTS conduct;

COMMIT;
