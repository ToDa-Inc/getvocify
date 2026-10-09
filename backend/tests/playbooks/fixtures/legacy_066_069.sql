-- The playbooks schema as migrations 066, 067, 068 and 069 left it (concatenated, in order), for the
-- test that 066_playbooks_v2.sql upgrades a database where they were already applied.

-- ===== 066_playbook_draft_autosave.sql
-- Playbook draft autosave. The editor now saves the draft in place instead of inserting one
-- playbook_versions row per save, and compares updated_at to notice that someone else changed
-- the draft (409 stale_draft). Existing rows start with updated_at = created_at.
-- Rollback: 066_playbook_draft_autosave.down.sql

BEGIN;

ALTER TABLE playbook_versions
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- Before the trigger exists, so the backfill does not stamp every row with "now".
UPDATE playbook_versions SET updated_at = created_at;

CREATE OR REPLACE FUNCTION playbook_versions_touch_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $touch$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$touch$;

DROP TRIGGER IF EXISTS playbook_versions_updated_at ON playbook_versions;
CREATE TRIGGER playbook_versions_updated_at
  BEFORE UPDATE ON playbook_versions
  FOR EACH ROW EXECUTE FUNCTION playbook_versions_touch_updated_at();

COMMIT;

-- ===== 067_playbook_rules.sql
-- Playbooks v2 (fase 2, T7): a label for the type and the rule that says which calls it applies to.
-- applies_to = {role: sdr|ae|any, channels: [call|meeting|visit], contact: new|contacted|inbound|any,
-- deal_stages: [crm stage id, ...]}. NULL on a catalog type means "the catalog's default rule".
-- Rollback: 067_playbook_rules.down.sql

BEGIN;

ALTER TABLE playbooks
  ADD COLUMN IF NOT EXISTS label TEXT,
  ADD COLUMN IF NOT EXISTS applies_to JSONB;

COMMIT;

-- ===== 068_playbook_three_layers.sql
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

-- ===== 069_playbook_pause_archive.sql
-- Playbooks: pause, resume and delete (soft, undoable) a call type
-- (docs/superpowers/plans/2026-09-29-playbooks-v2.md, section 16).
--   * Pausing moves playbooks.active_version_id to paused_version_id, so everything that reads the
--     active version (pinning a call, routing, copilot, briefs, insights) ignores the playbook with
--     no change. The content stays; memos already evaluated keep pointing at their version.
--   * Deleting sets archived_at and remembers the status before (archived_state) so it can be
--     undone; the API also moves the active version to paused_version_id, drops the pending drafts
--     and deactivates the interaction_types row.
--   * list_playbook_motions skips archived playbooks and answers 'paused' when there is no active
--     version but a paused one (a pending draft does not change that: details.has_draft tells the UI).
--   * Publishing (publish_playbook_version, publish_playbook_motion) clears the pause and the
--     archive; add_interaction_type on an archived type brings it back, without the old content.
-- Idempotent. Rollback: 069_playbook_pause_archive.down.sql

BEGIN;

ALTER TABLE playbooks
  ADD COLUMN IF NOT EXISTS paused_version_id UUID NULL,
  ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ NULL,
  ADD COLUMN IF NOT EXISTS archived_state TEXT NULL;

CREATE OR REPLACE FUNCTION publish_playbook_version(p_version UUID)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
  pb UUID;
BEGIN
  SELECT playbook_id INTO pb FROM playbook_versions WHERE id = p_version FOR UPDATE;
  IF pb IS NULL THEN
    RAISE EXCEPTION 'playbook version not found';
  END IF;
  PERFORM 1 FROM playbooks WHERE id = pb FOR UPDATE;
  UPDATE playbook_versions SET status = 'published' WHERE id = p_version;
  UPDATE playbooks
  SET active_version_id = p_version,
      paused_version_id = NULL,
      archived_at = NULL,
      archived_state = NULL
  WHERE id = pb;
  RETURN p_version;
END;
$$;

CREATE OR REPLACE FUNCTION publish_playbook_motion(p_company UUID, p_motion TEXT)
RETURNS TEXT
LANGUAGE plpgsql
AS $publish_motion$
DECLARE
  pb UUID;
  ver UUID;
BEGIN
  SELECT id INTO pb FROM playbooks
  WHERE company_id = p_company AND sales_motion_key = p_motion
  FOR UPDATE;

  IF pb IS NULL THEN
    RETURN 'not_a_draft';
  END IF;

  IF EXISTS (
    SELECT 1 FROM playbook_imports i
    WHERE i.playbook_id = pb
      AND COALESCE(jsonb_array_length(i.draft->'contradictions'), 0) > 0
      AND i.created_at = (
        SELECT max(created_at) FROM playbook_imports WHERE playbook_id = pb
      )
  ) THEN
    RETURN 'contradiction';
  END IF;

  SELECT id INTO ver FROM playbook_versions
  WHERE playbook_id = pb AND status = 'draft'
  ORDER BY created_at DESC
  LIMIT 1
  FOR UPDATE;

  IF ver IS NULL THEN
    RETURN 'not_a_draft';
  END IF;

  PERFORM publish_playbook_version(ver);
  -- Publishing lifts a pause and a delete (publish_playbook_version does it too; kept explicit).
  UPDATE playbooks
  SET paused_version_id = NULL, archived_at = NULL, archived_state = NULL
  WHERE id = pb;
  RETURN 'published:' || ver::text;
END;
$publish_motion$;

CREATE OR REPLACE FUNCTION list_playbook_motions(p_company UUID)
RETURNS TABLE (sales_motion_key TEXT, motion_status TEXT)
LANGUAGE sql
STABLE
AS $list_motions$
  SELECT motion_key AS sales_motion_key, motion_status
  FROM (
    SELECT p.sales_motion_key AS motion_key,
      CASE
        WHEN p.active_version_id IS NOT NULL THEN 'published'
        WHEN p.paused_version_id IS NOT NULL THEN 'paused'
        WHEN EXISTS (
          SELECT 1 FROM playbook_versions v
          WHERE v.playbook_id = p.id AND v.status = 'draft'
        ) THEN 'draft'
        ELSE 'missing'
      END AS motion_status
    FROM playbooks p
    WHERE p.company_id = p_company
      AND p.archived_at IS NULL
    UNION
    SELECT t.type_key,
      'missing'
    FROM interaction_types t
    WHERE t.company_id = p_company
      AND t.active
      AND NOT EXISTS (
        SELECT 1 FROM playbooks p
        WHERE p.company_id = t.company_id AND p.sales_motion_key = t.type_key
      )
  ) listed;
$list_motions$;

CREATE OR REPLACE FUNCTION add_interaction_type(p_company UUID, p_key TEXT, p_name TEXT)
RETURNS TEXT
LANGUAGE plpgsql
AS $add_type$
BEGIN
  IF btrim(p_key) = '' THEN
    RETURN 'empty';
  END IF;
  INSERT INTO interaction_types (company_id, type_key, name)
  VALUES (p_company, btrim(p_key), COALESCE(NULLIF(btrim(p_name), ''), btrim(p_key)))
  ON CONFLICT (company_id, type_key) DO UPDATE SET active = true;
  -- Creating a deleted type again brings it back empty: the old version is not resurrected.
  UPDATE playbooks
  SET archived_at = NULL, paused_version_id = NULL, archived_state = NULL
  WHERE company_id = p_company
    AND sales_motion_key = btrim(p_key)
    AND archived_at IS NOT NULL;
  RETURN btrim(p_key);
END;
$add_type$;

COMMIT;
