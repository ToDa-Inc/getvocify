import { api } from '@/shared/lib/api-client';
import type { CompanyDetails, CompanyMember, InvitePreview, PendingInvite } from './types';

function mapCompany(raw: Record<string, unknown>): CompanyDetails {
  return {
    id: String(raw.id),
    name: String(raw.name ?? ''),
    role: (raw.role as CompanyDetails['role']) ?? 'member',
    seatLimit: Number(raw.seat_limit ?? 1),
    seatsUsed: Number(raw.seats_used ?? 0),
    seatsPending: Number(raw.seats_pending ?? 0),
    seatsActive: Number(raw.seats_active ?? 0),
    seatsAvailable: Number(raw.seats_available ?? 0),
  };
}

function mapMember(raw: Record<string, unknown>): CompanyMember {
  return {
    id: String(raw.id),
    userId: String(raw.user_id),
    email: String(raw.email ?? ''),
    fullName: (raw.full_name as string) ?? null,
    role: String(raw.role),
    status: String(raw.status),
    createdAt: raw.created_at as string | undefined,
  };
}

function mapInvite(raw: Record<string, unknown>): PendingInvite {
  return {
    id: String(raw.id),
    email: String(raw.email),
    role: String(raw.role),
    expiresAt: String(raw.expires_at),
    createdAt: raw.created_at as string | undefined,
  };
}

export const companyKeys = {
  all: ['company'] as const,
  detail: () => [...companyKeys.all, 'detail'] as const,
  members: () => [...companyKeys.all, 'members'] as const,
};

export const companyApi = {
  get: async (): Promise<CompanyDetails> => {
    const raw = await api.get<Record<string, unknown>>('/company');
    return mapCompany(raw);
  },

  update: async (data: { name?: string }): Promise<CompanyDetails> => {
    const raw = await api.patch<Record<string, unknown>>('/company', {
      name: data.name,
    });
    return mapCompany(raw);
  },

  listMembers: async (): Promise<{ members: CompanyMember[]; pendingInvites: PendingInvite[] }> => {
    const raw = await api.get<Record<string, unknown>>('/company/members');
    const members = ((raw.members as Record<string, unknown>[]) ?? []).map(mapMember);
    const pendingInvites = ((raw.pending_invites as Record<string, unknown>[]) ?? []).map(mapInvite);
    return { members, pendingInvites };
  },

  invite: async (email: string, role: 'admin' | 'member' = 'member'): Promise<{ emailSent: boolean; inviteUrl?: string }> => {
    const raw = await api.post<Record<string, unknown>>('/company/invites', { email, role, send_email: true });
    return {
      emailSent: Boolean(raw.email_sent),
      inviteUrl: raw.invite_url as string | undefined,
    };
  },

  resendInvite: async (inviteId: string) => {
    return api.post<Record<string, unknown>>(`/company/invites/${inviteId}/resend`);
  },

  revokeInvite: async (inviteId: string) => {
    return api.delete<void>(`/company/invites/${inviteId}`);
  },

  removeMember: async (memberId: string) => {
    return api.delete<void>(`/company/members/${memberId}`);
  },

  updateMemberRole: async (memberId: string, role: string) => {
    return api.patch<Record<string, unknown>>(`/company/members/${memberId}`, { role });
  },

  previewInvite: async (token: string): Promise<InvitePreview> => {
    const raw = await api.get<Record<string, unknown>>(`/company/invites/preview?token=${encodeURIComponent(token)}`);
    return {
      email: String(raw.email),
      role: String(raw.role),
      companyName: (raw.company_name as string) ?? null,
      expiresAt: String(raw.expires_at),
      requiresPassword: Boolean(raw.requires_password),
    };
  },

  acceptInvite: async (token: string, password?: string, fullName?: string) => {
    return api.post<{ success: boolean; message: string }>('/company/invites/accept', {
      token,
      password,
      full_name: fullName,
    });
  },
};
