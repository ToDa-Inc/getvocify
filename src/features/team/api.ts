import { api } from '@/shared/lib/api-client';
import type { SalesRole } from '@/features/company/types';
import type {
  ActivityStats,
  MemberActivity,
  PeriodPreset,
  SalesRoleFilter,
  TeamMedian,
  TeamMetrics,
  TrendWeek,
} from './types';

type Raw = Record<string, unknown>;

const rate = (value: unknown): number | null => (value == null ? null : Number(value));

function mapStats(raw: Raw = {}): ActivityStats {
  return {
    calls: Number(raw.calls ?? 0),
    connected: Number(raw.connected ?? 0),
    voicemail: Number(raw.voicemail ?? 0),
    noAnswer: Number(raw.no_answer ?? 0),
    failed: Number(raw.failed ?? 0),
    unknown: Number(raw.unknown ?? 0),
    useful: Number(raw.useful ?? 0),
    talkSeconds: Number(raw.talk_seconds ?? 0),
    connectionRate: rate(raw.connection_rate),
    usefulRate: rate(raw.useful_rate),
  };
}

function mapMedian(raw: Raw = {}): TeamMedian {
  return {
    people: Number(raw.people ?? 0),
    calls: rate(raw.calls),
    connected: rate(raw.connected),
    useful: rate(raw.useful),
    connectionRate: rate(raw.connection_rate),
    usefulRate: rate(raw.useful_rate),
  };
}

function mapMember(raw: Raw): MemberActivity {
  return {
    userId: String(raw.user_id),
    name: String(raw.name ?? ''),
    email: String(raw.email ?? ''),
    salesRole: (raw.sales_role as SalesRole) ?? 'other',
    startedOn: (raw.started_on as string) ?? null,
    current: mapStats(raw.current as Raw),
    previous: mapStats(raw.previous as Raw),
  };
}

function mapMetrics(raw: Raw): TeamMetrics {
  const team = (raw.team as Raw) ?? {};
  const period = (raw.period as Raw) ?? {};
  const previous = (raw.previous_period as Raw) ?? {};
  const settings = (raw.settings as Raw) ?? {};
  return {
    preset: raw.preset as PeriodPreset,
    salesRole: raw.sales_role as SalesRoleFilter,
    generatedAt: String(raw.generated_at ?? new Date().toISOString()),
    period: { start: String(period.start), end: String(period.end) },
    previousPeriod: { start: String(previous.start), end: String(previous.end) },
    usefulCallSeconds: Number(settings.useful_call_seconds ?? 60),
    members: ((raw.members as Raw[]) ?? []).map(mapMember),
    team: {
      current: mapStats(team.current as Raw),
      previous: mapStats(team.previous as Raw),
      median: mapMedian(team.median as Raw),
    },
    trend: ((raw.trend as Raw[]) ?? []).map(
      (w): TrendWeek => ({
        weekStart: String(w.week_start),
        calls: Number(w.calls ?? 0),
        connected: Number(w.connected ?? 0),
        useful: Number(w.useful ?? 0),
      }),
    ),
    unavailable: ((raw.unavailable as Raw[]) ?? []).map((u) => ({
      metric: String(u.metric),
      reason: String(u.reason),
    })),
  };
}

export const teamKeys = {
  all: ['team'] as const,
  metrics: (period: PeriodPreset, salesRole: SalesRoleFilter) =>
    [...teamKeys.all, 'metrics', period, salesRole] as const,
};

export const teamApi = {
  getMetrics: async (period: PeriodPreset, salesRole: SalesRoleFilter): Promise<TeamMetrics> => {
    const params = new URLSearchParams({ period, sales_role: salesRole });
    const raw = await api.get<Raw>(`/team/metrics?${params.toString()}`);
    return mapMetrics(raw);
  },
};
