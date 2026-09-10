import { api } from '@/shared/lib/api-client';
import type { AddCallerIdResponse, CallingConfig } from './types';

export const callKeys = {
  all: ["calls"] as const,
  config: () => [...callKeys.all, "config"] as const,
};

function encodePhone(phoneNumber: string): string {
  return encodeURIComponent(phoneNumber);
}

export const callsApi = {
  getConfig: (): Promise<CallingConfig> => api.get<CallingConfig>('/calls/config'),

  createToken: (): Promise<{
    token: string;
    identity: string;
    expiresIn: number;
    provider?: string;
  }> => api.post('/calls/token', {}),

  getLatestDisposition: (): Promise<{
    disposition: string | null;
    status: string | null;
  }> => api.get('/calls/outbound/latest-disposition'),

  listCallerIds: (): Promise<{ callerIds: CallingConfig['callerIds'] }> =>
    api.get('/calls/caller-ids'),

  addCallerId: (phoneNumber: string, label?: string | null): Promise<AddCallerIdResponse> =>
    api.post<AddCallerIdResponse>('/calls/caller-ids', {
      phoneNumber,
      label: label || null,
    }),

  confirmCallerId: (
    phoneNumber: string,
    code: string,
  ): Promise<AddCallerIdResponse> =>
    api.post<AddCallerIdResponse>('/calls/caller-ids/confirm', {
      phoneNumber,
      code,
    }),

  setDefaultCallerId: (phoneNumber: string): Promise<{ callerIds: CallingConfig['callerIds'] }> =>
    api.patch(`/calls/caller-ids/${encodePhone(phoneNumber)}`, { isDefault: true }),

  deleteCallerId: (phoneNumber: string): Promise<{ ok: boolean }> =>
    api.delete(`/calls/caller-ids/${encodePhone(phoneNumber)}`),
};
