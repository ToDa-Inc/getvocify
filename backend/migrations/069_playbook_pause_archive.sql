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
