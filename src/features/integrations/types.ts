/**
 * Types for the Integrations feature
 * 
 * CRM connections, OAuth flows, and field mapping.
 */

import type { ID, ISODateString, Nullable } from '@/shared/types/common';

// ============================================
// PROVIDER TYPES
// ============================================

/**
 * Supported CRM providers
 * 
 * Note: Only HubSpot is implemented for MVP.
 * Salesforce and Pipedrive are planned for future releases.
 */
export type CRMProvider = 'hubspot' | 'salesforce' | 'pipedrive';

/**
 * CRM provider configuration
 */
export interface CRMProviderConfig {
  /** Provider identifier */
  id: CRMProvider;
  /** Display name */
  name: string;
  /** Logo URL */
  logo: string;
  /** Short description */
  description: string;
  /** Whether the integration is available */
  available: boolean;
  /** OAuth scopes required */
  scopes: string[];
}

/**
 * Provider configurations
 */
export const CRM_PROVIDER_CONFIGS: Record<CRMProvider, CRMProviderConfig> = {
  hubspot: {
    id: 'hubspot',
    name: 'HubSpot',
    logo: '/integrations/hubspot.svg',
    description: 'Connect your HubSpot CRM to sync deals and contacts',
    available: true,
    scopes: [
      'crm.objects.contacts.read',
      'crm.objects.contacts.write',
      'crm.objects.deals.read',
      'crm.objects.deals.write',
      'crm.objects.companies.read',
      'crm.objects.notes.write',
      'crm.schemas.deals.read',
    ],
  },
  salesforce: {
    id: 'salesforce',
    name: 'Salesforce',
    logo: '/integrations/salesforce.svg',
    description: 'Connect your Salesforce CRM to sync opportunities',
    available: false,
    scopes: [],
  },
  pipedrive: {
    id: 'pipedrive',
    name: 'Pipedrive',
    logo: '/integrations/pipedrive.svg',
    description: 'Connect your Pipedrive CRM to sync deals',
    available: false,
    scopes: [],
  },
};

// ============================================
// CONNECTION TYPES
// ============================================

/**
 * CRM connection status
 */
export type ConnectionStatus = 'connected' | 'expired' | 'error';

/**
 * CRM connection entity
 * 
 * Represents an OAuth connection to a CRM provider.
 */
export interface CRMConnection {
  /** Unique identifier */
  id: ID;
  /** Owner user ID */
  userId: ID;
  /** CRM provider */
  provider: CRMProvider;
  /** Connection status */
  status: ConnectionStatus;

  // ---- Provider Metadata ----
  /** Provider-specific metadata */
  metadata: CRMConnectionMetadata;

  // ---- Token State ----
  /** When the access token expires */
  tokenExpiresAt: Nullable<ISODateString>;
  /** When we last synced with this CRM */
  lastSyncedAt: Nullable<ISODateString>;

  // ---- Timestamps ----
  /** When the connection was created */
  createdAt: ISODateString;
}

/**
 * Provider-specific connection metadata
 */
export interface CRMConnectionMetadata {
  /** HubSpot portal ID */
  portalId?: string;
  /** Salesforce instance URL */
  instanceUrl?: string;
  /** Pipedrive company domain */
  companyDomain?: string;
  /** CRM user email */
  userEmail?: string;
  /** CRM user name */
  userName?: string;
}

/**
 * Check if a connection needs refresh
 */
export function connectionNeedsRefresh(connection: CRMConnection): boolean {
  if (!connection.tokenExpiresAt) return false;
  
  // Consider expired if less than 5 minutes remaining
  const expiresAt = new Date(connection.tokenExpiresAt);
  const fiveMinutes = 5 * 60 * 1000;
  return expiresAt.getTime() - Date.now() < fiveMinutes;
}

// ============================================
// CRM SCHEMA TYPES
// ============================================

/**
 * CRM field types
 */
export type CRMFieldType = 
  | 'string' 
  | 'number' 
  | 'date' 
  | 'datetime'
  | 'boolean'
  | 'select' 
  | 'multiselect'
  | 'textarea';

/**
 * CRM field definition
 * 
 * Represents a field in the CRM (e.g., HubSpot deal property).
 */
export interface CRMField {
  /** Internal field name */
  name: string;
  /** Display label */
  label: string;
  /** Field type */
  type: CRMFieldType;
  /** Whether the field is required */
  required: boolean;
  /** Options for select/multiselect fields */
  options?: CRMFieldOption[];
  /** Group/section this field belongs to */
  group?: string;
}

/**
 * Option for select/multiselect fields
 */
export interface CRMFieldOption {
  /** Option value */
  value: string;
  /** Display label */
  label: string;
}

/**
 * Pipeline stage definition
 */
export interface CRMPipelineStage {
  /** Stage ID */
  id: string;
  /** Display label */
  label: string;
  /** Display order */
  displayOrder: number;
  /** Whether this is the default stage */
  isDefault?: boolean;
  /** Whether this is a closed stage */
  isClosed?: boolean;
  /** Win/loss indicator for closed stages */
  probability?: number;
}

/**
 * CRM deal schema
 * 
 * Fetched from the connected CRM to enable dynamic field mapping.
 */
export interface CRMDealSchema {
  /** Deal properties/fields */
  properties: CRMField[];
  /** Pipeline stages */
  stages: CRMPipelineStage[];
  /** Pipeline ID */
  pipelineId: string;
  /** Pipeline name */
  pipelineName: string;
}

// ============================================
// API TYPES
// ============================================

/**
 * Response from OAuth authorize endpoint
 */
export interface OAuthAuthorizeResponse {
  /** URL to redirect user to */
  authorizationUrl: string;
}

/**
 * Test connection result
 */
export interface TestConnectionResult {
  /** Whether the connection is working */
  success: boolean;
  /** Error message if failed */
  error?: string;
  /** Connection details if successful */
  details?: {
    userName: string;
    userEmail: string;
    accountName: string;
  };
}


