/**
 * CRM call recordings API.
 *
 * Uses HubSpot endpoints today — the only CRM with a recordings list in the backend.
 */

import { api } from '@/shared/lib/api-client';
import type { CrmCallRecording, ProcessCallRecordingResponse } from './types';

export const recordingKeys = {
  all: ['recordings'] as const,
  list: (limit = 20, authorUserId?: string | null) =>
    [...recordingKeys.all, 'list', limit, authorUserId ?? ''] as const,
};

export const recordingsApi = {
  /** Recent calls with recordings across the connected CRM portal. */
  list: (limit = 20, authorUserId?: string | null): Promise<CrmCallRecording[]> => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (authorUserId) params.set('author_user_id', authorUserId);
    return api.get<CrmCallRecording[]>(`/crm/hubspot/recordings?${params}`);
  },

  /** Start or retry transcription for a call recording. */
  process: (callId: string): Promise<ProcessCallRecordingResponse> => {
    return api.post<ProcessCallRecordingResponse>(`/crm/hubspot/calls/${callId}/process`);
  },
};
