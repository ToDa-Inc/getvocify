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
  /** T1/D3: the current user's own visibility ('own'/'team'). Only set when
   * SALES_ROLES_ENABLED; a member with 'team' also reads /dashboard/insights. */
  visibility?: MemberVisibility | null;
  /** Company flags on for this company (Lista 3), e.g. 'SALES_ROLES_ENABLED'. */
  features?: string[];
  /** D10: the Head of Sales's sales strategy. Only set when FOLLOWUP_BY_FLOW_ENABLED. */
  salesStrategy?: string | null;
  /** T5: days after an unanswered call before Hoy suggests calling back. Only set when
   * HOY_LEAD_TIERS_ENABLED. */
  callbackAfterDays?: number | null;
  /** T9: owner/admin whose company hasn't finished the onboarding wizard yet.
   * Only meaningful when ONBOARDING_WIZARD_ENABLED; false for members and off by default. */
  needsOnboarding?: boolean;
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

/** T9: the onboarding wizard's steps, in the order it walks the Head of Sales through. */
export type OnboardingStep = 'crm' | 'team' | 'handoff' | 'playbooks' | 'strategy';

export interface InvitePreview {
  email: string;
  role: string;
  salesRole?: SalesRole | null;
  companyName: string | null;
  expiresAt: string;
  requiresPassword: boolean;
}
