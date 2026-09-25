-- F08: playbook versions. One active snapshot per playbook. Older versions stay readable.

CREATE TABLE IF NOT EXISTS playbooks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL,
  sales_motion_key TEXT NOT NULL,
  active_version_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (company_id, sales_motion_key)
);

CREATE TABLE IF NOT EXISTS playbook_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  playbook_id UUID NOT NULL REFERENCES playbooks(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published')),
  steps JSONB NOT NULL DEFAULT '[]'::jsonb,
  entries JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS playbook_imports (
  id TEXT PRIMARY KEY,
  company_id UUID,
  playbook_id UUID,
  kind TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending', 'ready', 'failed')),
  reason TEXT,
  draft JSONB,
  active_version_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS interaction_types (
  company_id UUID NOT NULL,
  type_key TEXT NOT NULL,
  name TEXT NOT NULL,
  active BOOLEAN NOT NULL DEFAULT true,
  PRIMARY KEY (company_id, type_key)
);

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
  UPDATE playbooks SET active_version_id = p_version WHERE id = pb;
  RETURN p_version;
END;
$$;

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
  WHERE company_id = p_company AND sales_motion_key = p_motion;

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
        WHEN EXISTS (
          SELECT 1 FROM playbook_versions v
          WHERE v.playbook_id = p.id AND v.status = 'draft'
        ) THEN 'draft'
        ELSE 'missing'
      END AS motion_status
    FROM playbooks p
    WHERE p.company_id = p_company
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
  ON CONFLICT (company_id, type_key) DO NOTHING;
  RETURN btrim(p_key);
END;
$add_type$;

