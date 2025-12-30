/**
 * Integrations feature barrel export
 */

// Types
export * from './types';

// API
export { integrationsApi, integrationKeys } from './api';

// Hooks
export { 
  useIntegrations, 
  useConnection,
  useDealSchema,
  useDisconnect,
  useTestConnection,
  useConnectCRM,
} from './hooks';


