import type { SalesRole } from '@/features/company/types';

export type PeriodPreset = 'week' | 'month' | 'last_30' | 'quarter';
export type SalesRoleFilter = 'all' | 'sdr' | 'ae';

/** Activity for one person or the team over one period. Rates are null without data, never 0. */
export interface ActivityStats {
  calls: number;
  connected: number;
  voicemail: number;
  noAnswer: number;
  failed: number;
  unknown: number;
  useful: number;
  talkSeconds: number;
  connectionRate: number | null;
  usefulRate: number | null;
}

export interface TeamMedian {
  people: number;
  calls: number | null;
  connected: number | null;
  useful: number | null;
  connectionRate: number | null;
  usefulRate: number | null;
}

export interface MemberActivity {
  userId: string;
  name: string;
  email: string;
  salesRole: SalesRole;
  startedOn: string | null;
  current: ActivityStats;
  previous: ActivityStats;
}

export interface TrendWeek {
  weekStart: string;
  calls: number;
  connected: number;
  useful: number;
}

export interface TeamMetrics {
  preset: PeriodPreset;
  salesRole: SalesRoleFilter;
  generatedAt: string;
  period: { start: string; end: string };
  previousPeriod: { start: string; end: string };
  usefulCallSeconds: number;
  members: MemberActivity[];
  team: { current: ActivityStats; previous: ActivityStats; median: TeamMedian };
  trend: TrendWeek[];
  unavailable: { metric: string; reason: string }[];
}
