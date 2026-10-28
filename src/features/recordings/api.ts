import { api } from '@/shared/lib/api-client';
import type { CrmCallRecording, ProcessCallRecordingResponse, UnansweredOutcome } from './types';

export const recordingKeys = {
  all: ['crm-recordings'] as const,
  recent: (authorUserId: string | null) => [...recordingKeys.all, 'recent', authorUserId ?? 'all'] as const,
};

/** How far back the dashboard lists the CRM's calls; every call of those days, not only the newest few. */
export const RECENT_CALL_DAYS = 7;
const RECENT_CALL_LIMIT = 200;

export const recordingsApi = {
  /** HubSpot calls with a recording of the viewer's scope over the last `days`, with the Vocify memo each one already
   * has; calls the rep recorded on the desktop are left out. */
  listRecent: (authorUserId: string | null, days = RECENT_CALL_DAYS): Promise<CrmCallRecording[]> => {
    const params = new URLSearchParams({
      limit: String(RECENT_CALL_LIMIT),
      days: String(days),
      hide_desktop_recorded: 'true',
    });
    if (authorUserId) params.set('author_user_id', authorUserId);
    return api.get<CrmCallRecording[]>(`/crm/hubspot/recordings?${params}`);
  },

  /** Start (or retry) transcription of one HubSpot call. */
  process: (callId: string): Promise<ProcessCallRecordingResponse> =>
    api.post<ProcessCallRecordingResponse>(`/crm/hubspot/calls/${encodeURIComponent(callId)}/process`, {}),

  /** Keep one HubSpot call as no answer (or voicemail) without transcribing it. */
  markUnanswered: (callId: string, outcome: UnansweredOutcome): Promise<ProcessCallRecordingResponse> =>
    api.post<ProcessCallRecordingResponse>(`/crm/hubspot/calls/${encodeURIComponent(callId)}/mark-unanswered`, { outcome }),
};
