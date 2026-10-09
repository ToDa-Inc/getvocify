import { api } from '@/shared/lib/api-client';

export interface MeetingBotResult {
  captureId: string;
  memoId: string;
  botId: string;
  status: string;
}

// T14: sends a Recall.ai bot into a Zoom/Meet/Teams meeting. Behind RECALL_BOT_ENABLED
// (see user.company.features); the backend also 404s if the flag is off.
export const meetingsApi = {
  createBot: async (meetingUrl: string, contactId?: string): Promise<MeetingBotResult> => {
    const raw = await api.post<Record<string, unknown>>('/meetings/bot', {
      meeting_url: meetingUrl,
      contact_id: contactId,
    });
    return {
      captureId: String(raw.capture_id),
      memoId: String(raw.memo_id),
      botId: String(raw.bot_id),
      status: String(raw.status),
    };
  },
};
