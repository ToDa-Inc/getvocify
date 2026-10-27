import { api } from '@/shared/lib/api-client';
import type { CrmCallRecording, ProcessCallRecordingResponse } from './types';

export const recordingKeys = {
  all: ['crm-recordings'] as const,
  recent: (authorUserId: string | null) => [...recordingKeys.all, 'recent', authorUserId ?? 'all'] as const,
};

export const recordingsApi = {
  /** Newest HubSpot calls that have a recording, with the Vocify memo each one already has; calls the rep recorded on the desktop are left out. */
  listRecent: (authorUserId: string | null, limit = 20): Promise<CrmCallRecording[]> => {
    const params = new URLSearchParams({ limit: String(limit), hide_desktop_recorded: 'true' });
    if (authorUserId) params.set('author_user_id', authorUserId);
    return api.get<CrmCallRecording[]>(`/crm/hubspot/recordings?${params}`);
  },

  /** Start (or retry) transcription of one HubSpot call. */
  process: (callId: string): Promise<ProcessCallRecordingResponse> =>
    api.post<ProcessCallRecordingResponse>(`/crm/hubspot/calls/${encodeURIComponent(callId)}/process`, {}),
};
