-- Per-connection whitelist for HubSpot line item properties (mirrors deal/contact/company).
ALTER TABLE crm_configurations
  ADD COLUMN IF NOT EXISTS allowed_line_item_fields TEXT[]
  DEFAULT ARRAY['name', 'quantity', 'price'];

-- Allow caching HubSpot line_items schemas alongside deals/contacts/companies.
ALTER TABLE crm_schemas DROP CONSTRAINT IF EXISTS crm_schemas_object_type_check;
ALTER TABLE crm_schemas ADD CONSTRAINT crm_schemas_object_type_check CHECK (
  object_type IN (
    'deals', 'contacts', 'companies', 'line_items',
    'Opportunity', 'Contact', 'Account'
  )
);
