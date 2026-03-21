-- Allow Salesforce sObject API names in crm_schemas cache (in addition to HubSpot object_type values)
ALTER TABLE crm_schemas DROP CONSTRAINT IF EXISTS crm_schemas_object_type_check;
ALTER TABLE crm_schemas ADD CONSTRAINT crm_schemas_object_type_check CHECK (
  object_type IN (
    'deals', 'contacts', 'companies',
    'Opportunity', 'Contact', 'Account'
  )
);
