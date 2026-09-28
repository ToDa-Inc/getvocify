import { api } from '@/shared/lib/api-client';
import { mapAuthResponse } from '@/features/auth/api';
import type { AuthResponse } from '@/features/auth/types';
import type {
  CompanyDetails,
  CompanyMember,
  InvitePreview,
  PendingInvite,
  SalesRole,
  SalesSettings,
} from './types';

const SALES_ROLES: readonly SalesRole[] = ['sdr', 'ae', 'manager', 'other'];

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
    accessMode: String(raw.access_mode ?? 'open'),
    billingStatus: String(raw.billing_status ?? 'none'),
    planType: raw.plan_type === 'starter' || raw.plan_type === 'pro' ? raw.plan_type : null,
    paywalled: Boolean(raw.paywalled),
    canUseDialer: raw.can_use_dialer == null ? true : Boolean(raw.can_use_dialer),
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
    salesRole: SALES_ROLES.includes(raw.sales_role as SalesRole) ? (raw.sales_role as SalesRole) : 'other',
    startedOn: (raw.started_on as string) ?? null,
  };
}

function mapSalesSettings(raw: Record<string, unknown>): SalesSettings {
  return { usefulCallSeconds: Number(raw.useful_call_seconds ?? 60) };
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
  salesSettings: () => [...companyKeys.all, 'sales-settings'] as const,
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

  updateSalesProfile: async (
    memberId: string,
    data: { salesRole?: SalesRole; startedOn?: string | null },
  ): Promise<CompanyMember> => {
    const body: Record<string, unknown> = {};
    if (data.salesRole !== undefined) body.sales_role = data.salesRole;
    if (data.startedOn !== undefined) body.started_on = data.startedOn;
    const raw = await api.patch<Record<string, unknown>>(`/company/members/${memberId}/sales-profile`, body);
    return mapMember(raw);
  },

  getSalesSettings: async (): Promise<SalesSettings> => {
    const raw = await api.get<Record<string, unknown>>('/company/sales-settings');
    return mapSalesSettings(raw);
  },

  updateSalesSettings: async (data: SalesSettings): Promise<SalesSettings> => {
    const raw = await api.patch<Record<string, unknown>>('/company/sales-settings', {
      useful_call_seconds: data.usefulCallSeconds,
    });
    return mapSalesSettings(raw);
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

  acceptInvite: async (token: string, password?: string, fullName?: string): Promise<AuthResponse> => {
    const raw = await api.post<Record<string, unknown>>('/company/invites/accept', {
      token,
      password,
      full_name: fullName,
    });
    return mapAuthResponse(raw);
  },
};
