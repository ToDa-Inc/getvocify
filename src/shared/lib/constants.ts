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
  HIGH: 0.9,    // Auto-approve threshold
  MEDIUM: 0.7,  // Needs review
  LOW: 0.5,     // Likely wrong, highlight
} as const;

// Memo status display
export const MEMO_STATUS_CONFIG = {
  uploading: {
    label: 'Uploading',
    color: 'text-blue-600',
    bgColor: 'bg-blue-100',
  },
  transcribing: {
    label: 'Transcribing',
    color: 'text-blue-600',
    bgColor: 'bg-blue-100',
  },
  extracting: {
    label: 'Extracting',
    color: 'text-purple-600',
    bgColor: 'bg-purple-100',
  },
  pending_review: {
    label: 'Pending Review',
    color: 'text-amber-600',
    bgColor: 'bg-amber-100',
  },
  approved: {
    label: 'Approved',
    color: 'text-green-600',
    bgColor: 'bg-green-100',
  },
  rejected: {
    label: 'Rejected',
    color: 'text-gray-600',
    bgColor: 'bg-gray-100',
  },
  failed: {
    label: 'Failed',
    color: 'text-red-600',
    bgColor: 'bg-red-100',
  },
} as const;

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
    comingSoon: true,
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
  INTEGRATIONS: '/dashboard/integrations',
  PROFILE: '/dashboard/profile',
  SETTINGS: '/dashboard/settings',
  USAGE: '/dashboard/usage',
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


