/**
 * Application-wide constants
 */

// Audio recording constraints
export const AUDIO = {
  MAX_DURATION_SECONDS: 180, // 3 minutes
  MIN_DURATION_SECONDS: 5,   // Minimum useful recording
  MAX_FILE_SIZE_BYTES: 10 * 1024 * 1024, // 10MB
  SUPPORTED_FORMATS: ['audio/webm', 'audio/mp3', 'audio/mpeg', 'audio/wav', 'audio/m4a'],
  PREFERRED_FORMAT: 'audio/webm',
} as const;

// Confidence thresholds for extraction
export const CONFIDENCE = {
  HIGH: 0.9,    // Confident extraction — green/red in review
  MEDIUM: 0.7,  // Needs review
  LOW: 0.5,     // Below this, backend drops the field
} as const;

export function isUncertainExtractionConfidence(confidence: number | null | undefined): boolean {
  if (confidence == null || !Number.isFinite(confidence)) return false;
  return confidence >= CONFIDENCE.LOW && confidence < CONFIDENCE.HIGH;
}

// CRM providers
export const CRM_PROVIDERS = {
  hubspot: {
    name: 'HubSpot',
    logo: '/integrations/hubspot.svg',
    description: 'Connect your HubSpot CRM to sync deals and contacts',
  },
  salesforce: {
    name: 'Salesforce',
    logo: '/integrations/salesforce.svg',
    description: 'Connect your Salesforce CRM to sync opportunities',
    comingSoon: true,
  },
  pipedrive: {
    name: 'Pipedrive',
    logo: '/integrations/pipedrive.svg',
    description: 'Connect your Pipedrive CRM to sync deals',
    comingSoon: false,
  },
} as const;

// Routes
export const ROUTES = {
  HOME: '/',
  LOGIN: '/auth/login',
  SIGNUP: '/auth/signup',
  DASHBOARD: '/dashboard',
  RECORD: '/dashboard/record',
  MEMOS: '/dashboard/memos',
  MEMO_DETAIL: (id: string) => `/dashboard/memos/${id}`,
  INTEGRATIONS: '/dashboard/settings',
  PROFILE: '/dashboard/profile',
  SETTINGS: '/dashboard/settings',
  CALLING: '/dashboard/settings/calling#caller-id',
  USAGE: '/dashboard/settings/usage',
  COPILOT: '/dashboard/copilot',
} as const;

// Pagination defaults
export const PAGINATION = {
  DEFAULT_PAGE_SIZE: 20,
  MAX_PAGE_SIZE: 100,
} as const;

// Time formatting
export const TIME = {
  SECONDS_PER_MINUTE: 60,
  SECONDS_PER_HOUR: 3600,
} as const;


