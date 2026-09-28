import { api } from '@/shared/lib/api-client';
import { mapAuthResponse } from '@/features/auth/api';
import type { AuthResponse } from '@/features/auth/types';
import type {
  CompanyDetails,
  CompanyMember,
  InvitePreview,
  MemberVisibility,
  OnboardingStep,
  PendingInvite,
  SalesRole,
} from './types';

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
    repWorkspace: Boolean(raw.rep_workspace_enabled),
    briefV2: Boolean(raw.brief_v2_enabled),
    salesStrategy: (raw.sales_strategy as string | null | undefined) ?? null,
    callbackAfterDays: typeof raw.callback_after_days === 'number' ? raw.callback_after_days : null,
    needsOnboarding: Boolean(raw.needs_onboarding),
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
    salesRole: (raw.sales_role as SalesRole | null | undefined) ?? null,
    handoffAeUserId: (raw.handoff_ae_user_id as string | null | undefined) ?? null,
    visibility: (raw.visibility as MemberVisibility | undefined) ?? 'own',
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

  update: async (data: { name?: string; salesStrategy?: string; callbackAfterDays?: number }): Promise<CompanyDetails> => {
    const raw = await api.patch<Record<string, unknown>>('/company', {
      name: data.name,
      sales_strategy: data.salesStrategy,
      callback_after_days: data.callbackAfterDays,
    });
    return mapCompany(raw);
  },

  listMembers: async (): Promise<{ members: CompanyMember[]; pendingInvites: PendingInvite[] }> => {
    const raw = await api.get<Record<string, unknown>>('/company/members');
    const members = ((raw.members as Record<string, unknown>[]) ?? []).map(mapMember);
    const pendingInvites = ((raw.pending_invites as Record<string, unknown>[]) ?? []).map(mapInvite);
    return { members, pendingInvites };
  },

  invite: async (
    email: string,
    role: 'admin' | 'member' = 'member',
    salesRole?: SalesRole,
  ): Promise<{ emailSent: boolean; inviteUrl?: string; crmOwnerMatch: boolean | null }> => {
    const raw = await api.post<Record<string, unknown>>('/company/invites', {
      email,
      role,
      send_email: true,
      sales_role: salesRole,
    });
    return {
      emailSent: Boolean(raw.email_sent),
      inviteUrl: raw.invite_url as string | undefined,
      crmOwnerMatch: (raw.crm_owner_match as boolean | null | undefined) ?? null,
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

  updateMemberSalesProfile: async (
    memberId: string,
    profile: { salesRole?: SalesRole | null; handoffAeUserId?: string | null; visibility?: MemberVisibility },
  ) => {
    const body: Record<string, unknown> = {};
    if ('salesRole' in profile) body.sales_role = profile.salesRole;
    if ('handoffAeUserId' in profile) body.handoff_ae_user_id = profile.handoffAeUserId;
    if ('visibility' in profile) body.visibility = profile.visibility;
    return api.patch<Record<string, unknown>>(`/company/members/${memberId}`, body);
  },

  previewInvite: async (token: string): Promise<InvitePreview> => {
    const raw = await api.get<Record<string, unknown>>(`/company/invites/preview?token=${encodeURIComponent(token)}`);
    return {
      email: String(raw.email),
      role: String(raw.role),
      salesRole: (raw.sales_role as SalesRole | null | undefined) ?? null,
      companyName: (raw.company_name as string) ?? null,
      expiresAt: String(raw.expires_at),
      requiresPassword: Boolean(raw.requires_password),
    };
  },

  /** T9: which onboarding step the wizard should show next (owner/admin only). */
  getOnboardingState: async (): Promise<{
    needed: boolean;
    nextStep: OnboardingStep | null;
    state: Record<OnboardingStep, boolean>;
  }> => {
    const raw = await api.get<Record<string, unknown>>('/company/onboarding');
    return {
      needed: Boolean(raw.needed),
      nextStep: (raw.next_step as OnboardingStep | null) ?? null,
      state: (raw.state as Record<OnboardingStep, boolean>) ?? ({} as Record<OnboardingStep, boolean>),
    };
  },

  /** T9: finish (or skip through) the onboarding wizard. */
  completeOnboarding: async (): Promise<CompanyDetails> => {
    const raw = await api.post<Record<string, unknown>>('/company/onboarding/complete');
    return mapCompany(raw);
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
