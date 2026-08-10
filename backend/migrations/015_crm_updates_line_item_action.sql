-- Allow line item sync actions (and keep existing sync action types).
ALTER TABLE crm_updates
DROP CONSTRAINT IF EXISTS crm_updates_action_type_check;

ALTER TABLE crm_updates
ADD CONSTRAINT crm_updates_action_type_check
CHECK (action_type IN (
  'create_deal',
  'update_deal',
  'upsert_company',
  'upsert_contact',
  'merge_tasks',
  'create_tasks',
  'create_note',
  'create_line_item'
));
