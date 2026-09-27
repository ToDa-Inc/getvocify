/**
 * Company workspace types
 */

import type { SalesRole } from '@/lib/sales-role';

export type { SalesRole };

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
  /** Present only when SALES_ROLES_ENABLED is on for the company. */
  salesRole?: SalesRole;
}

export interface CompanyDetails extends CompanySummary {
  seatsActive: number;
  seatsAvailable: number;
}

export interface CompanyMember {
  id: string;
  userId: string;
  email: string;
  fullName: string | null;
  role: string;
  status: string;
  createdAt?: string;
  /** Present only when SALES_ROLES_ENABLED is on for the company. */
  salesRole?: SalesRole;
}

export interface PendingInvite {
  id: string;
  email: string;
  role: string;
  expiresAt: string;
  createdAt?: string;
  /** Present only when SALES_ROLES_ENABLED is on for the company. */
  salesRole?: SalesRole;
}

export interface InvitePreview {
  email: string;
  role: string;
  companyName: string | null;
  expiresAt: string;
  requiresPassword: boolean;
}
