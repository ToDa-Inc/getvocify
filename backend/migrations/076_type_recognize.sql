-- Types by channel (docs/superpowers/specs/2026-10-07-interaction-types-by-channel-design.md):
-- one optional sentence per type, "how to recognise it", read by the live suggestion and the call
-- reading. Nullable, no backfill: a type without it is described by its name and playbook steps.
-- playbook_set_meta and playbook_overview are the 066 functions plus this one field.
-- Rollback: 076_type_recognize.down.sql

BEGIN;

ALTER TABLE playbooks ADD COLUMN IF NOT EXISTS recognize TEXT;

-- The name, rule and/or recognition sentence of a type. p_meta carries only the keys to set:
-- {"label": text|null, "applies_to": object|null, "recognize": text|null}. Creates the playbooks row when
-- the type has none (listed as 'missing'). Returns the key.
CREATE OR REPLACE FUNCTION playbook_set_meta(p_company UUID, p_motion TEXT, p_meta JSONB)
RETURNS TEXT
LANGUAGE plpgsql
AS $set_meta$
BEGIN
  INSERT INTO playbooks (company_id, sales_motion_key)
  VALUES (p_company, p_motion)
  ON CONFLICT (company_id, sales_motion_key) DO NOTHING;

  UPDATE playbooks
  SET label = CASE WHEN p_meta ? 'label' THEN NULLIF(p_meta->>'label', '') ELSE label END,
      applies_to = CASE WHEN p_meta ? 'applies_to' THEN NULLIF(p_meta->'applies_to', 'null'::jsonb) ELSE applies_to END,
      recognize = CASE WHEN p_meta ? 'recognize' THEN NULLIF(btrim(p_meta->>'recognize'), '') ELSE recognize END
  WHERE company_id = p_company AND sales_motion_key = p_motion;
  RETURN p_motion;
END;
$set_meta$;

-- The types of the company, one entry each: {key, status, label, applies_to, recognize, has_draft, paused, version}.
CREATE OR REPLACE FUNCTION playbook_overview(p_company UUID, p_include_draft BOOLEAN DEFAULT true)
RETURNS JSONB
LANGUAGE sql
STABLE
AS $overview$
  SELECT COALESCE(jsonb_agg(entry ORDER BY entry->>'key'), '[]'::jsonb)
  FROM (
    SELECT jsonb_build_object(
      'key', l.sales_motion_key,
      'status', l.motion_status,
      'label', p.label,
      'applies_to', p.applies_to,
      'recognize', p.recognize,
      'has_draft', p_include_draft AND pend.id IS NOT NULL,
      'paused', l.motion_status = 'paused',
      'version', CASE
        WHEN p_include_draft AND pend.id IS NOT NULL THEN playbook_version_json(pend.id)
        WHEN p.active_version_id IS NOT NULL THEN playbook_version_json(p.active_version_id)
        ELSE NULL
      END
    ) AS entry
    FROM list_playbook_motions(p_company) l
    LEFT JOIN playbooks p
      ON p.company_id = p_company AND p.sales_motion_key = l.sales_motion_key
    LEFT JOIN LATERAL (SELECT playbook_pending_draft(p.id) AS id) pend ON true
  ) entries;
$overview$;

COMMIT;
