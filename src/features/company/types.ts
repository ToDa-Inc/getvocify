/**
 * Company workspace types
 */

export interface CompanySummary {
  id: string;
  name: string;
  role: 'owner' | 'admin' | 'member';
  seatLimit: number;
  seatsUsed: number;
  seatsPending: number;
  accessMode?: 'open' | 'paywalled' | 'unlocked' | string;
  billingStatus?: string;
  planType?: 'starter' | 'pro' | null;
  paywalled?: boolean;
  canUseDialer?: boolean;
  repWorkspace?: boolean;
  briefV2?: boolean;
  /** The current user's own sales_role. Only set when SALES_ROLES_ENABLED. */
  salesRole?: SalesRole | null;
  /** Company flags on for this company (Lista 3), e.g. 'SALES_ROLES_ENABLED'. */
  features?: string[];
}

export interface CompanyDetails extends CompanySummary {
  seatsActive: number;
  seatsAvailable: number;
}

/** D1: independent of `role` (owner/admin/member). null behaves as 'general'. */
export type SalesRole = 'sdr' | 'ae' | 'general';

/** D3: 'team' grants read of the team's activity, no management permissions. */
export type MemberVisibility = 'own' | 'team';

export interface CompanyMember {
  id: string;
  userId: string;
  email: string;
  fullName: string | null;
  role: string;
  status: string;
  createdAt?: string;
  /** Only present when SALES_ROLES_ENABLED for this company. */
  salesRole?: SalesRole | null;
  handoffAeUserId?: string | null;
  visibility?: MemberVisibility;
}

export interface PendingInvite {
  id: string;
  email: string;
  role: string;
  expiresAt: string;
  createdAt?: string;
}

export interface InvitePreview {
  email: string;
  role: string;
  companyName: string | null;
  expiresAt: string;
  requiresPassword: boolean;
}
