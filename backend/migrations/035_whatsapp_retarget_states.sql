ALTER TABLE conversations DROP CONSTRAINT IF EXISTS conversations_state_check;
ALTER TABLE conversations ADD CONSTRAINT conversations_state_check CHECK (
  state IN (
    'idle',
    'waiting_approval',
    'waiting_add_fields',
    'waiting_crm_instruction',
    'waiting_deal_choice',
    'waiting_retarget',
    'waiting_typed_search'
  )
);
