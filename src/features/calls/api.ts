import { api } from '@/shared/lib/api-client';
import type { AddCallerIdResponse, CallingConfig } from './types';

function encodePhone(phoneNumber: string): string {
  return encodeURIComponent(phoneNumber);
}

export const callsApi = {
  getConfig: (): Promise<CallingConfig> => api.get<CallingConfig>('/calls/config'),

  listCallerIds: (): Promise<{ callerIds: CallingConfig['callerIds'] }> =>
    api.get('/calls/caller-ids'),

  addCallerId: (phoneNumber: string, label?: string | null): Promise<AddCallerIdResponse> =>
    api.post<AddCallerIdResponse>('/calls/caller-ids', {
      phoneNumber,
      label: label || null,
    }),

  setDefaultCallerId: (phoneNumber: string): Promise<{ callerIds: CallingConfig['callerIds'] }> =>
    api.patch(`/calls/caller-ids/${encodePhone(phoneNumber)}`, { isDefault: true }),

  deleteCallerId: (phoneNumber: string): Promise<{ ok: boolean }> =>
    api.delete(`/calls/caller-ids/${encodePhone(phoneNumber)}`),
};
