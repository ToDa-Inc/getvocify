/**
 * Integrations API
 * 
 * All API calls related to CRM integrations.
 */

import { api } from '@/shared/lib/api-client';
import type {
  CRMProvider,
  CRMConnection,
  CRMDealSchema,
  OAuthAuthorizeResponse,
  TestConnectionResult,
} from './types';

/**
 * Query keys for TanStack Query
 */
export const integrationKeys = {
  all: ['integrations'] as const,
  connections: () => [...integrationKeys.all, 'connections'] as const,
  connection: (provider: CRMProvider) => [...integrationKeys.connections(), provider] as const,
  schemas: () => [...integrationKeys.all, 'schemas'] as const,
  schema: (provider: CRMProvider) => [...integrationKeys.schemas(), provider] as const,
};

/**
 * Integrations API methods
 */
export const integrationsApi = {
  // ============================================
  // CONNECTIONS
  // ============================================

  /**
   * List all CRM connections for the current user
   */
  listConnections: (): Promise<CRMConnection[]> => {
    return api.get<CRMConnection[]>('/crm/connections');
  },

  /**
   * Get a specific connection
   */
  getConnection: (provider: CRMProvider): Promise<CRMConnection | null> => {
    return api.get<CRMConnection | null>(`/crm/${provider}/connection`);
  },

  /**
   * Disconnect a CRM
   */
  disconnect: (provider: CRMProvider): Promise<void> => {
    return api.post<void>(`/crm/${provider}/disconnect`);
  },

  /**
   * Test a connection
   */
  testConnection: (provider: CRMProvider): Promise<TestConnectionResult> => {
    return api.post<TestConnectionResult>(`/crm/${provider}/test`);
  },

  // ============================================
  // OAUTH
  // ============================================

  /**
   * Get OAuth authorization URL
   * 
   * Returns a URL to redirect the user to for OAuth consent.
   */
  getAuthorizationUrl: (provider: CRMProvider): Promise<OAuthAuthorizeResponse> => {
    return api.get<OAuthAuthorizeResponse>(`/crm/${provider}/authorize`);
  },

  // ============================================
  // SCHEMA
  // ============================================

  /**
   * Get the deal schema from a connected CRM
   * 
   * Returns the deal properties and pipeline stages.
   * Used for dynamic field mapping in the approval workflow.
   */
  getDealSchema: (provider: CRMProvider): Promise<CRMDealSchema> => {
    return api.get<CRMDealSchema>(`/crm/${provider}/schema`);
  },
};


