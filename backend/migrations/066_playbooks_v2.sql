-- Playbooks v2: the whole schema of the playbooks feature in one migration
-- (docs/superpowers/plans/2026-09-29-playbooks-v2.md, section 17). It replaces 066_playbook_draft_autosave,
-- 067_playbook_rules, 068_playbook_three_layers and 069_playbook_pause_archive.
--
-- WHAT IT LEAVES
--   playbooks           label, applies_to (the type's name and its "when it applies" rule);
--                       state ('active' | 'paused': the on/off switch, it never touches the version);
--                       archived_at (soft delete, independent of the switch).
--                       active_version_id means ONE thing again: the published version.
--   playbook_versions   updated_at (bumped by a trigger: the editor's stale-draft check), qualification.
--   company_sales_knowledge  what Vocify knows about the company, once (+ updated_at trigger).
--   playbooks_live      THE definition of "what applies to a call":
--                       active_version_id IS NOT NULL AND state = 'active' AND archived_at IS NULL.
--                       Nothing outside services/playbooks/live.py reads active_version_id to decide that.
--
-- IDEMPOTENT, AND SAFE ON A DATABASE WHERE THE OLD 066-069 WERE ALREADY APPLIED
--   Missing columns are added. If playbooks.paused_version_id exists (the 069 shape) it is folded in first:
--   a paused playbook gets state = 'paused' and its version back as active_version_id; a deleted one keeps
--   archived_at and gets the state it had (archived_state), so "restore" still brings it back as it was.
--   Then paused_version_id and archived_state are dropped. A second run changes nothing.
--
-- ERROR CONVENTION (every function below)
--   A business outcome that is not success is RAISED: RAISE EXCEPTION '<code>' (SQLSTATE P0001), the message
--   IS the code and nothing else. Success returns data. PostgREST hands the code to the client as
--   the error's `message`; services/playbooks/repository.py maps it to a typed exception. Codes:
--     stale_draft      the draft moved since the caller loaded it (base_updated_at no longer matches)
--     stale_knowledge  the company knowledge moved since the caller loaded it
--     not_published    pause: there is no active version to pause (or it is not on)
--     not_paused       resume: it is not paused
--     not_archived     restore: it is not deleted
--     not_found        delete: the company has no such type
--     not_a_draft      publish: nothing pending to publish
--     contradiction    publish: the latest import has contradictions
--     empty_type       add a type with an empty key
--     invalid_type_item / invalid_action   malformed input
--   Timestamps handed in by a client are compared to the millisecond (a browser round trip through a JS Date
--   loses the microseconds).
--
-- Rollback: 066_playbooks_v2.down.sql (a paused playbook is live again, see there)

BEGIN;

-- ─── columns ────────────────────────────────────────────────────────────────────────────────

ALTER TABLE playbooks
  ADD COLUMN IF NOT EXISTS label TEXT,
  ADD COLUMN IF NOT EXISTS applies_to JSONB,
  ADD COLUMN IF NOT EXISTS state TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'paused')),
  ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ NULL;

DO $add_updated_at$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = current_schema() AND table_name = 'playbook_versions' AND column_name = 'updated_at'
  ) THEN
    ALTER TABLE playbook_versions ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
    -- Only when the column is new: the trigger is not there yet, so the backfill does not stamp "now".
    UPDATE playbook_versions SET updated_at = created_at;
  END IF;
END
$add_updated_at$;

ALTER TABLE playbook_versions
  ADD COLUMN IF NOT EXISTS qualification JSONB NOT NULL DEFAULT '[]'::jsonb;

CREATE TABLE IF NOT EXISTS company_sales_knowledge (
  company_id UUID PRIMARY KEY,
  data JSONB NOT NULL DEFAULT '{}'::jsonb,
  source_id TEXT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- From the 069 shape (paused_version_id / archived_state) to state + archived_at. Runs once: the columns
-- are dropped right after.
DO $fold_069$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = current_schema() AND table_name = 'playbooks' AND column_name = 'paused_version_id'
  ) THEN
    EXECUTE $fold$
      UPDATE playbooks
      SET state = CASE
            WHEN active_version_id IS NULL AND (archived_at IS NULL OR archived_state = 'paused') THEN 'paused'
            ELSE 'active'
          END,
          active_version_id = COALESCE(active_version_id, paused_version_id)
      WHERE paused_version_id IS NOT NULL
    $fold$;
  END IF;
END
$fold_069$;

ALTER TABLE playbooks
  DROP COLUMN IF EXISTS paused_version_id,
  DROP COLUMN IF EXISTS archived_state;

-- ─── updated_at triggers ────────────────────────────────────────────────────────────────────
-- Strictly later than the row's previous value (by more than the millisecond the stale checks compare
-- at), so two quick saves never share a timestamp.

CREATE OR REPLACE FUNCTION playbook_versions_touch_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $touch$
BEGIN
  NEW.updated_at = GREATEST(clock_timestamp(), OLD.updated_at + interval '2 milliseconds');
  RETURN NEW;
END;
$touch$;

DROP TRIGGER IF EXISTS playbook_versions_updated_at ON playbook_versions;
CREATE TRIGGER playbook_versions_updated_at
  BEFORE UPDATE ON playbook_versions
  FOR EACH ROW EXECUTE FUNCTION playbook_versions_touch_updated_at();

CREATE OR REPLACE FUNCTION company_sales_knowledge_touch_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $touch$
BEGIN
  NEW.updated_at = GREATEST(clock_timestamp(), OLD.updated_at + interval '2 milliseconds');
  RETURN NEW;
END;
$touch$;

DROP TRIGGER IF EXISTS company_sales_knowledge_updated_at ON company_sales_knowledge;
CREATE TRIGGER company_sales_knowledge_updated_at
  BEFORE UPDATE ON company_sales_knowledge
  FOR EACH ROW EXECUTE FUNCTION company_sales_knowledge_touch_updated_at();

-- ─── playbooks_live: what applies to a call ─────────────────────────────────────────────────

CREATE OR REPLACE VIEW playbooks_live AS
SELECT
  p.id AS playbook_id,
  p.company_id,
  p.sales_motion_key,
  p.active_version_id AS version_id
FROM playbooks p
WHERE p.active_version_id IS NOT NULL
  AND p.state = 'active'
  AND p.archived_at IS NULL;

-- ─── helpers ────────────────────────────────────────────────────────────────────────────────

-- The pending draft of a playbook: its latest draft row, when it is newer than the active version (or there
-- is no active version). An older draft left behind (by an earlier publish, or by the one-row-per-save era)
-- is not "the draft".
CREATE OR REPLACE FUNCTION playbook_pending_draft(p_playbook UUID)
RETURNS UUID
LANGUAGE sql
STABLE
AS $pending$
  SELECT v.id
  FROM playbook_versions v
  WHERE v.playbook_id = p_playbook
    AND v.status = 'draft'
    AND (
      NOT EXISTS (
        SELECT 1 FROM playbooks p WHERE p.id = p_playbook AND p.active_version_id IS NOT NULL
      )
      OR v.created_at > (
        SELECT a.created_at
        FROM playbooks p JOIN playbook_versions a ON a.id = p.active_version_id
        WHERE p.id = p_playbook
      )
    )
  ORDER BY v.created_at DESC
  LIMIT 1;
$pending$;

-- A deleted type that is written to again comes back empty: the old published version is not resurrected
-- (it stays as a row nothing points at) and the old drafts were deleted with it.
CREATE OR REPLACE FUNCTION playbook_unarchive(p_playbook UUID)
RETURNS VOID
LANGUAGE sql
AS $unarchive$
  UPDATE playbooks
  SET archived_at = NULL, active_version_id = NULL, state = 'active'
  WHERE id = p_playbook AND archived_at IS NOT NULL;
$unarchive$;

-- A source document ({id, kind, name}) of the company; NULL for anything else.
CREATE OR REPLACE FUNCTION playbook_source_view(p_company UUID, p_source_id TEXT)
RETURNS JSONB
LANGUAGE sql
STABLE
AS $source_view$
  SELECT jsonb_build_object('id', i.id, 'kind', i.kind, 'name', COALESCE(i.draft->>'name', ''))
  FROM playbook_imports i
  WHERE i.id = p_source_id
    AND p_source_id LIKE 'source:%'
    AND i.company_id = p_company;
$source_view$;

CREATE OR REPLACE FUNCTION playbook_version_json(p_version UUID)
RETURNS JSONB
LANGUAGE sql
STABLE
AS $version_json$
  SELECT jsonb_build_object(
    'id', v.id, 'status', v.status, 'steps', v.steps, 'entries', v.entries,
    'qualification', v.qualification, 'created_at', v.created_at, 'updated_at', v.updated_at
  )
  FROM playbook_versions v
  WHERE v.id = p_version;
$version_json$;

-- ─── the 040 functions, updated ─────────────────────────────────────────────────────────────

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
  -- Publishing turns the playbook on and lifts a delete.
  UPDATE playbooks
  SET active_version_id = p_version, state = 'active', archived_at = NULL
  WHERE id = pb;
  RETURN p_version;
END;
$$;

-- The legacy text import (POST /playbooks/imports): a draft made of the whole document. Idempotent per import id.
CREATE OR REPLACE FUNCTION save_playbook_draft(
  p_company UUID,
  p_motion TEXT,
  p_import TEXT,
  p_payload TEXT,
  p_contradictions JSONB DEFAULT '[]'::jsonb
) RETURNS TEXT
LANGUAGE plpgsql
AS $save_draft$
DECLARE
  pb UUID;
BEGIN
  INSERT INTO playbooks (company_id, sales_motion_key)
  VALUES (p_company, p_motion)
  ON CONFLICT (company_id, sales_motion_key) DO NOTHING;

  SELECT id INTO pb FROM playbooks
  WHERE company_id = p_company AND sales_motion_key = p_motion
  FOR UPDATE;

  PERFORM playbook_unarchive(pb);

  IF EXISTS (SELECT 1 FROM playbook_imports WHERE id = p_import) THEN
    RETURN 'ready';
  END IF;

  INSERT INTO playbook_versions (playbook_id, status, steps, entries)
  VALUES (
    pb,
    'draft',
    jsonb_build_array(jsonb_build_object(
      'step_id', 'imported',
      'label', left(p_payload, 80),
      'criterion', p_payload
    )),
    jsonb_build_array(jsonb_build_object(
      'entry_id', 'text:' || p_import,
      'category', 'process',
      'guidance', p_payload,
      'source_ref', 'text:' || p_import
    ))
  );

  INSERT INTO playbook_imports (
    id, company_id, playbook_id, kind, status, draft, active_version_id
  )
  VALUES (
    p_import,
    p_company,
    pb,
    'text',
    'ready',
    jsonb_build_object(
      'text', p_payload,
      'source_ref', 'text:' || p_import,
      'contradictions', COALESCE(p_contradictions, '[]'::jsonb)
    ),
    (SELECT active_version_id FROM playbooks WHERE id = pb)
  );
  RETURN 'ready';
END;
$save_draft$;

-- Publishes the pending draft. Returns 'published:<version id>'.
-- Raises: not_a_draft (no such type, deleted, or nothing pending), contradiction.
CREATE OR REPLACE FUNCTION publish_playbook_motion(p_company UUID, p_motion TEXT)
RETURNS TEXT
LANGUAGE plpgsql
AS $publish_motion$
DECLARE
  pb playbooks%ROWTYPE;
  ver UUID;
BEGIN
  SELECT * INTO pb FROM playbooks
  WHERE company_id = p_company AND sales_motion_key = p_motion
  FOR UPDATE;

  IF NOT FOUND OR pb.archived_at IS NOT NULL THEN
    RAISE EXCEPTION 'not_a_draft';
  END IF;

  IF EXISTS (
    SELECT 1 FROM playbook_imports i
    WHERE i.playbook_id = pb.id
      AND COALESCE(jsonb_array_length(i.draft->'contradictions'), 0) > 0
      AND i.created_at = (
        SELECT max(created_at) FROM playbook_imports WHERE playbook_id = pb.id
      )
  ) THEN
    RAISE EXCEPTION 'contradiction';
  END IF;

  ver := playbook_pending_draft(pb.id);
  IF ver IS NULL THEN
    RAISE EXCEPTION 'not_a_draft';
  END IF;

  PERFORM publish_playbook_version(ver);
  RETURN 'published:' || ver::text;
END;
$publish_motion$;

-- Status per type: published | paused (published, switched off) | draft | missing. Deleted types are not there;
-- a type that only lives in interaction_types (no playbooks row) is 'missing'.
CREATE OR REPLACE FUNCTION list_playbook_motions(p_company UUID)
RETURNS TABLE (sales_motion_key TEXT, motion_status TEXT)
LANGUAGE sql
STABLE
AS $list_motions$
  SELECT motion_key AS sales_motion_key, motion_status
  FROM (
    SELECT p.sales_motion_key AS motion_key,
      CASE
        WHEN p.active_version_id IS NOT NULL AND p.state = 'paused' THEN 'paused'
        WHEN p.active_version_id IS NOT NULL THEN 'published'
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

-- Adds a type (or turns a deleted one back on, empty). Returns the key. Raises: empty_type.
CREATE OR REPLACE FUNCTION add_interaction_type(p_company UUID, p_key TEXT, p_name TEXT)
RETURNS TEXT
LANGUAGE plpgsql
AS $add_type$
BEGIN
  IF btrim(p_key) = '' THEN
    RAISE EXCEPTION 'empty_type';
  END IF;
  INSERT INTO interaction_types (company_id, type_key, name)
  VALUES (p_company, btrim(p_key), COALESCE(NULLIF(btrim(p_name), ''), btrim(p_key)))
  ON CONFLICT (company_id, type_key) DO UPDATE SET active = true;
  -- Creating a deleted type again brings it back empty: the old version is not resurrected.
  PERFORM playbook_unarchive(id)
  FROM playbooks
  WHERE company_id = p_company AND sales_motion_key = btrim(p_key);
  RETURN btrim(p_key);
END;
$add_type$;

-- ─── writes ─────────────────────────────────────────────────────────────────────────────────

-- The name and/or the rule of a type. p_meta carries only the keys to set: {"label": text|null,
-- "applies_to": object|null}. Creates the playbooks row when the type has none (listed as 'missing'). Returns the key.
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
      applies_to = CASE WHEN p_meta ? 'applies_to' THEN NULLIF(p_meta->'applies_to', 'null'::jsonb) ELSE applies_to END
  WHERE company_id = p_company AND sales_motion_key = p_motion;
  RETURN p_motion;
END;
$set_meta$;

-- add_interaction_type plus, in the same transaction, the type's name and rule when p_meta is given.
-- Returns the key. Raises: empty_type.
CREATE OR REPLACE FUNCTION playbook_add_type(p_company UUID, p_key TEXT, p_name TEXT, p_meta JSONB DEFAULT NULL)
RETURNS TEXT
LANGUAGE plpgsql
AS $add_playbook_type$
DECLARE
  k TEXT := btrim(COALESCE(p_key, ''));
BEGIN
  PERFORM add_interaction_type(p_company, k, p_name);
  IF p_meta IS NOT NULL AND jsonb_typeof(p_meta) = 'object' THEN
    PERFORM playbook_set_meta(p_company, k, p_meta);
  END IF;
  RETURN k;
END;
$add_playbook_type$;

-- Saves the editor's draft of a type and returns the saved playbook_versions row.
--   * The playbook row is created if needed; a deleted one is un-archived first (empty, switched on).
--   * A pending draft is UPDATED in place (same version id, autosave keeps one row). The conflict check is
--     part of that UPDATE: WHERE updated_at = p_base_updated_at. Otherwise a new draft is inserted; with a
--     base given that must be the active version's updated_at (a first save over a live version).
--   * p_qualification NULL leaves the draft's criteria as they are; a new draft starts from the live one's.
--   * p_source_id is kept only if it is a source document of this company.
--   * The draft has ONE import row (kind 'editor', id editor:<version id>, no contradictions), created with
--     it and rewritten by later saves; it becomes the playbook's latest import, so a contradictory legacy
--     import stops blocking publishing once the editor has saved over it. p_text is the plain-text copy
--     the caller renders for it (audit).
-- Raises: stale_draft.
CREATE OR REPLACE FUNCTION playbook_save_draft(
  p_company UUID,
  p_motion TEXT,
  p_steps JSONB,
  p_entries JSONB,
  p_qualification JSONB,
  p_source_id TEXT,
  p_base_updated_at TIMESTAMPTZ,
  p_text TEXT DEFAULT NULL
) RETURNS playbook_versions
LANGUAGE plpgsql
AS $save_draft_v2$
DECLARE
  pb playbooks%ROWTYPE;
  live playbook_versions%ROWTYPE;
  pending UUID;
  v playbook_versions%ROWTYPE;
  src TEXT := NULL;
  prior JSONB;
  had_import BOOLEAN;
  effective TEXT;
  import_draft JSONB;
BEGIN
  INSERT INTO playbooks (company_id, sales_motion_key)
  VALUES (p_company, p_motion)
  ON CONFLICT (company_id, sales_motion_key) DO NOTHING;

  -- The playbook row serializes every save of this type.
  SELECT * INTO pb FROM playbooks
  WHERE company_id = p_company AND sales_motion_key = p_motion
  FOR UPDATE;

  IF pb.archived_at IS NOT NULL THEN
    PERFORM playbook_unarchive(pb.id);
    SELECT * INTO pb FROM playbooks WHERE id = pb.id;
  END IF;

  IF p_source_id IS NOT NULL AND playbook_source_view(p_company, p_source_id) IS NOT NULL THEN
    src := p_source_id;
  END IF;

  SELECT * INTO live FROM playbook_versions WHERE id = pb.active_version_id;
  pending := playbook_pending_draft(pb.id);

  IF pending IS NOT NULL THEN
    UPDATE playbook_versions
    SET steps = p_steps,
        entries = p_entries,
        qualification = COALESCE(p_qualification, qualification)
    WHERE id = pending
      AND status = 'draft'
      AND (
        p_base_updated_at IS NULL
        OR date_trunc('milliseconds', updated_at) = date_trunc('milliseconds', p_base_updated_at)
      )
    RETURNING * INTO v;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'stale_draft';
    END IF;
  ELSE
    IF p_base_updated_at IS NOT NULL AND (
      live.id IS NULL
      OR date_trunc('milliseconds', live.updated_at) <> date_trunc('milliseconds', p_base_updated_at)
    ) THEN
      RAISE EXCEPTION 'stale_draft';
    END IF;
    INSERT INTO playbook_versions (playbook_id, status, steps, entries, qualification)
    VALUES (pb.id, 'draft', p_steps, p_entries, COALESCE(p_qualification, live.qualification, '[]'::jsonb))
    RETURNING * INTO v;
  END IF;

  SELECT draft INTO prior FROM playbook_imports WHERE id = 'editor:' || v.id;
  had_import := FOUND;
  effective := COALESCE(src, prior->>'source_id');
  IF effective IS NULL AND NOT had_import AND live.id IS NOT NULL THEN
    -- The first edit over a published version keeps pointing at its source.
    SELECT draft->>'source_id' INTO effective FROM playbook_imports WHERE id = 'editor:' || live.id;
  END IF;
  import_draft := jsonb_build_object(
    'text', COALESCE(p_text, ''),
    'source_ref', 'editor',
    'contradictions', '[]'::jsonb,
    'version_id', v.id
  );
  IF effective IS NOT NULL THEN
    import_draft := import_draft || jsonb_build_object('source_id', effective);
  END IF;
  INSERT INTO playbook_imports (id, company_id, playbook_id, kind, status, draft, active_version_id, created_at)
  VALUES ('editor:' || v.id, p_company, pb.id, 'editor', 'ready', import_draft, pb.active_version_id, clock_timestamp())
  ON CONFLICT (id) DO UPDATE SET draft = EXCLUDED.draft, created_at = EXCLUDED.created_at;

  RETURN v;
END;
$save_draft_v2$;

-- Deletes the pending drafts (every draft newer than the active version, or all of them when there is none)
-- and their editor import rows. Published versions and source documents stay. Returns whether anything was deleted.
CREATE OR REPLACE FUNCTION playbook_discard_draft(p_company UUID, p_motion TEXT)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $discard$
DECLARE
  pb playbooks%ROWTYPE;
  ids UUID[];
BEGIN
  SELECT * INTO pb FROM playbooks
  WHERE company_id = p_company AND sales_motion_key = p_motion
  FOR UPDATE;
  IF NOT FOUND THEN
    RETURN false;
  END IF;

  SELECT COALESCE(array_agg(v.id), ARRAY[]::UUID[]) INTO ids
  FROM playbook_versions v
  WHERE v.playbook_id = pb.id
    AND v.status = 'draft'
    AND (
      pb.active_version_id IS NULL
      OR v.created_at > (SELECT a.created_at FROM playbook_versions a WHERE a.id = pb.active_version_id)
    );
  IF cardinality(ids) = 0 THEN
    RETURN false;
  END IF;

  DELETE FROM playbook_imports
  WHERE kind = 'editor' AND id IN (SELECT 'editor:' || x FROM unnest(ids) AS x);
  DELETE FROM playbook_versions WHERE id = ANY(ids) AND status = 'draft';
  RETURN true;
END;
$discard$;

-- The on/off switch and the soft delete of a type. p_action:
--   pause    (raises not_published unless there is an active version and the playbook is on)
--   resume   (raises not_paused unless it is paused)
--   archive  ("Eliminar": deletes the pending drafts and their editor imports, sets archived_at, turns the
--            interaction type off; works for a type that only lives in interaction_types; raises not_found
--            when the company has neither)
--   restore  (raises not_archived unless it is deleted; clears archived_at and turns the interaction type
--            on; `state` is untouched, so a paused one comes back paused and an active one active)
-- Returns the action that was applied.
CREATE OR REPLACE FUNCTION playbook_set_state(p_company UUID, p_motion TEXT, p_action TEXT)
RETURNS TEXT
LANGUAGE plpgsql
AS $set_state$
DECLARE
  pb playbooks%ROWTYPE;
  has_row BOOLEAN;
BEGIN
  IF p_action NOT IN ('pause', 'resume', 'archive', 'restore') THEN
    RAISE EXCEPTION 'invalid_action';
  END IF;

  SELECT * INTO pb FROM playbooks
  WHERE company_id = p_company AND sales_motion_key = p_motion
  FOR UPDATE;
  has_row := FOUND;

  IF p_action = 'pause' THEN
    IF NOT has_row OR pb.archived_at IS NOT NULL OR pb.active_version_id IS NULL OR pb.state <> 'active' THEN
      RAISE EXCEPTION 'not_published';
    END IF;
    UPDATE playbooks SET state = 'paused' WHERE id = pb.id;

  ELSIF p_action = 'resume' THEN
    IF NOT has_row OR pb.archived_at IS NOT NULL OR pb.active_version_id IS NULL OR pb.state <> 'paused' THEN
      RAISE EXCEPTION 'not_paused';
    END IF;
    UPDATE playbooks SET state = 'active' WHERE id = pb.id;

  ELSIF p_action = 'archive' THEN
    IF has_row AND pb.archived_at IS NULL THEN
      -- Drafts and their import rows first: a half-done delete would leave nothing hidden.
      DELETE FROM playbook_imports
      WHERE kind = 'editor'
        AND id IN (SELECT 'editor:' || v.id FROM playbook_versions v WHERE v.playbook_id = pb.id AND v.status = 'draft');
      DELETE FROM playbook_versions WHERE playbook_id = pb.id AND status = 'draft';
      UPDATE playbooks SET archived_at = now() WHERE id = pb.id;
    ELSIF has_row OR NOT EXISTS (
      SELECT 1 FROM interaction_types t
      WHERE t.company_id = p_company AND t.type_key = p_motion AND t.active
    ) THEN
      RAISE EXCEPTION 'not_found';
    END IF;
    UPDATE interaction_types SET active = false WHERE company_id = p_company AND type_key = p_motion;

  ELSE
    IF has_row THEN
      IF pb.archived_at IS NULL THEN
        RAISE EXCEPTION 'not_archived';
      END IF;
      UPDATE playbooks SET archived_at = NULL WHERE id = pb.id;
    ELSIF NOT EXISTS (
      SELECT 1 FROM interaction_types t
      WHERE t.company_id = p_company AND t.type_key = p_motion AND NOT t.active
    ) THEN
      RAISE EXCEPTION 'not_archived';
    END IF;
    UPDATE interaction_types SET active = true WHERE company_id = p_company AND type_key = p_motion;
  END IF;

  RETURN p_action;
END;
$set_state$;

-- What Vocify knows about the company (no draft: a save takes effect at once). The caller sends the data
-- already normalized. p_source_id NULL keeps the saved one. With p_base_updated_at the check is part of the
-- write: it applies only if the row still has that updated_at, and a base with no row is stale too.
-- Returns the saved row. Raises: stale_knowledge.
CREATE OR REPLACE FUNCTION company_knowledge_save(
  p_company UUID,
  p_data JSONB,
  p_source_id TEXT,
  p_base_updated_at TIMESTAMPTZ
) RETURNS company_sales_knowledge
LANGUAGE plpgsql
AS $knowledge_save$
DECLARE
  k company_sales_knowledge%ROWTYPE;
BEGIN
  IF p_base_updated_at IS NULL THEN
    INSERT INTO company_sales_knowledge (company_id, data, source_id)
    VALUES (p_company, COALESCE(p_data, '{}'::jsonb), p_source_id)
    ON CONFLICT (company_id) DO UPDATE
    SET data = EXCLUDED.data,
        source_id = COALESCE(EXCLUDED.source_id, company_sales_knowledge.source_id)
    RETURNING * INTO k;
  ELSE
    UPDATE company_sales_knowledge
    SET data = COALESCE(p_data, '{}'::jsonb),
        source_id = COALESCE(p_source_id, source_id)
    WHERE company_id = p_company
      AND date_trunc('milliseconds', updated_at) = date_trunc('milliseconds', p_base_updated_at)
    RETURNING * INTO k;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'stale_knowledge';
    END IF;
  END IF;
  RETURN k;
END;
$knowledge_save$;

-- One input for the whole company, in ONE transaction: every detected type's draft (playbook_save_draft) and
-- the company knowledge (already merged by the caller; NULL = none). If anything fails nothing is saved.
-- p_types: [{key, steps, entries, qualification (null = keep), text, ensure: {name, meta} (optional)}].
-- `ensure` creates the type first when the company does not have it yet (a catalog type found in the document).
-- Returns {types: [{sales_motion_key, version_id}], knowledge: row | null}. Raises: invalid_type_item.
CREATE OR REPLACE FUNCTION playbook_intake_save(
  p_company UUID,
  p_types JSONB,
  p_knowledge JSONB,
  p_source_id TEXT
) RETURNS JSONB
LANGUAGE plpgsql
AS $intake_save$
DECLARE
  item JSONB;
  ensure JSONB;
  v playbook_versions%ROWTYPE;
  saved JSONB := '[]'::jsonb;
  k company_sales_knowledge%ROWTYPE;
  knowledge JSONB := NULL;
BEGIN
  FOR item IN SELECT value FROM jsonb_array_elements(COALESCE(p_types, '[]'::jsonb))
  LOOP
    IF jsonb_typeof(item) <> 'object'
       OR COALESCE(btrim(item->>'key'), '') = ''
       OR jsonb_typeof(item->'steps') IS DISTINCT FROM 'array'
       OR jsonb_typeof(item->'entries') IS DISTINCT FROM 'array' THEN
      RAISE EXCEPTION 'invalid_type_item';
    END IF;

    ensure := item->'ensure';
    IF ensure IS NOT NULL AND jsonb_typeof(ensure) = 'object' AND NOT EXISTS (
      SELECT 1 FROM list_playbook_motions(p_company) l WHERE l.sales_motion_key = item->>'key'
    ) THEN
      PERFORM playbook_add_type(p_company, item->>'key', COALESCE(ensure->>'name', item->>'key'), ensure->'meta');
    END IF;

    v := playbook_save_draft(
      p_company,
      item->>'key',
      item->'steps',
      item->'entries',
      CASE WHEN jsonb_typeof(item->'qualification') = 'array' THEN item->'qualification' ELSE NULL END,
      p_source_id,
      NULL,
      item->>'text'
    );
    saved := saved || jsonb_build_array(jsonb_build_object('sales_motion_key', item->>'key', 'version_id', v.id));
  END LOOP;

  IF p_knowledge IS NOT NULL AND jsonb_typeof(p_knowledge) = 'object' THEN
    k := company_knowledge_save(p_company, p_knowledge, p_source_id, NULL);
    knowledge := to_jsonb(k);
  END IF;

  RETURN jsonb_build_object('types', saved, 'knowledge', knowledge);
END;
$intake_save$;

-- Keeps the original material a playbook was structured from (an import row, id source:<uuid>). Creates no
-- version. p_motion NULL = a document for the whole company: no playbooks row is created for it (that would
-- list a phantom call type). Returns {id, kind, name}.
CREATE OR REPLACE FUNCTION playbook_source_save(
  p_company UUID,
  p_motion TEXT,
  p_kind TEXT,
  p_name TEXT,
  p_text TEXT
) RETURNS JSONB
LANGUAGE plpgsql
AS $source_save$
DECLARE
  pb playbooks%ROWTYPE;
  sid TEXT := 'source:' || gen_random_uuid()::text;
BEGIN
  IF p_motion IS NOT NULL THEN
    INSERT INTO playbooks (company_id, sales_motion_key)
    VALUES (p_company, p_motion)
    ON CONFLICT (company_id, sales_motion_key) DO NOTHING;
    SELECT * INTO pb FROM playbooks WHERE company_id = p_company AND sales_motion_key = p_motion;
  END IF;
  INSERT INTO playbook_imports (id, company_id, playbook_id, kind, status, draft, active_version_id)
  VALUES (
    sid, p_company, pb.id, p_kind, 'ready',
    jsonb_build_object('text', p_text, 'name', COALESCE(p_name, ''), 'source_ref', p_kind || ':' || sid),
    pb.active_version_id
  );
  RETURN jsonb_build_object('id', sid, 'kind', p_kind, 'name', COALESCE(p_name, ''));
END;
$source_save$;

-- ─── reads (jsonb, so the repository needs nothing but rpc) ─────────────────────────────────

-- The types of the company, one entry each: {key, status, label, applies_to, has_draft, paused, version}.
-- `version` is the one the editor opens: the pending draft when p_include_draft (managers), else the
-- active version (also when it is paused); null when the type has neither. has_draft is false for a rep.
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

-- What the editor shows for one type: {state, version, has_live, source, paused}. state is 'draft' (the
-- pending draft, only when p_include_draft), 'published' (the active version, also when paused) or 'empty'
-- (also for a deleted type). source = the material the shown version was structured from, or null.
CREATE OR REPLACE FUNCTION playbook_editor(p_company UUID, p_motion TEXT, p_include_draft BOOLEAN DEFAULT true)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
AS $editor$
DECLARE
  pb playbooks%ROWTYPE;
  pend UUID := NULL;
  shown UUID := NULL;
  st TEXT := 'empty';
  recorded TEXT;
BEGIN
  SELECT * INTO pb FROM playbooks
  WHERE company_id = p_company AND sales_motion_key = p_motion;
  IF NOT FOUND OR pb.archived_at IS NOT NULL THEN
    RETURN jsonb_build_object('state', 'empty', 'version', NULL, 'has_live', false, 'source', NULL, 'paused', false);
  END IF;

  IF p_include_draft THEN
    pend := playbook_pending_draft(pb.id);
  END IF;
  IF pend IS NOT NULL THEN
    st := 'draft';
    shown := pend;
  ELSIF pb.active_version_id IS NOT NULL THEN
    st := 'published';
    shown := pb.active_version_id;
  END IF;

  IF shown IS NOT NULL THEN
    SELECT draft->>'source_id' INTO recorded FROM playbook_imports WHERE id = 'editor:' || shown;
  END IF;

  RETURN jsonb_build_object(
    'state', st,
    'version', CASE WHEN shown IS NULL THEN NULL ELSE playbook_version_json(shown) END,
    'has_live', pb.active_version_id IS NOT NULL,
    'source', CASE WHEN recorded IS NULL THEN NULL ELSE playbook_source_view(p_company, recorded) END,
    'paused', pb.active_version_id IS NOT NULL AND pb.state = 'paused'
  );
END;
$editor$;

CREATE OR REPLACE FUNCTION playbook_source_get(p_company UUID, p_source_id TEXT)
RETURNS JSONB
LANGUAGE sql
STABLE
AS $source_get$
  SELECT playbook_source_view(p_company, p_source_id);
$source_get$;

CREATE OR REPLACE FUNCTION playbook_import_get(p_company UUID, p_import TEXT)
RETURNS JSONB
LANGUAGE sql
STABLE
AS $import_get$
  SELECT jsonb_build_object(
    'id', i.id, 'import_id', i.id, 'kind', i.kind, 'status', i.status, 'draft', i.draft,
    'active_version_id', i.active_version_id, 'published', false
  )
  FROM playbook_imports i
  WHERE i.id = p_import AND i.company_id = p_company;
$import_get$;

CREATE OR REPLACE FUNCTION company_knowledge_get(p_company UUID)
RETURNS JSONB
LANGUAGE sql
STABLE
AS $knowledge_get$
  SELECT jsonb_build_object('data', k.data, 'source_id', k.source_id, 'updated_at', k.updated_at)
  FROM company_sales_knowledge k
  WHERE k.company_id = p_company;
$knowledge_get$;

COMMIT;
