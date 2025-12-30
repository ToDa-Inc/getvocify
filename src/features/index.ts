/**
 * Features barrel export
 * 
 * Note: Import from specific features when possible for better tree-shaking.
 * e.g., import { useMemos } from '@/features/memos'
 */

// Re-export features (be selective to avoid circular dependencies)
export { AuthProvider, useAuth } from './auth';
export { useMemos, useMemo } from './memos';
export { useMediaRecorder, useAudioUpload } from './recording';
export { useIntegrations, useConnectCRM } from './integrations';


