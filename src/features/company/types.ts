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
