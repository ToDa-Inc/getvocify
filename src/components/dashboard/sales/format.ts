import type { SalesRole } from '@/features/company/types';
import type { PeriodPreset } from '@/features/team/types';

export const PERIOD_OPTIONS: { value: PeriodPreset; label: string; comparison: string }[] = [
  { value: 'week', label: 'This week', comparison: 'same days last week' },
  { value: 'month', label: 'This month to date', comparison: 'same days last month' },
  { value: 'last_30', label: 'Last 30 days', comparison: 'previous 30 days' },
  { value: 'quarter', label: 'This quarter to date', comparison: 'same stretch last quarter' },
];

export const SALES_ROLE_LABEL: Record<SalesRole, string> = {
  sdr: 'SDR',
  ae: 'AE',
  manager: 'Manager',
  other: 'Other',
};

const numberFormat = new Intl.NumberFormat('en-GB');

export function formatCount(value: number | null | undefined, digits = 0): string {
  if (value == null) return '—';
  return digits ? value.toFixed(digits) : numberFormat.format(Math.round(value));
}

/** Medians can be halves: keep one decimal instead of rounding 3.5 up to 4. */
export function formatMedian(value: number | null | undefined): string {
  if (value == null) return '—';
  return new Intl.NumberFormat('en-GB', { maximumFractionDigits: 1 }).format(value);
}

export function formatPercent(rate: number | null | undefined): string {
  if (rate == null) return '—';
  return `${Math.round(rate * 100)}%`;
}

export function formatDayRange(startIso: string, endIso: string): string {
  const fmt = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short' });
  return `${fmt.format(new Date(startIso))} – ${fmt.format(new Date(endIso))}`;
}

export function formatWeek(iso: string): string {
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short' }).format(new Date(iso));
}

export type Delta = { text: string; direction: 'up' | 'down' | 'flat' } | null;

/** Change in a count vs the previous period. Null when there is nothing to compare. */
export function countDelta(current: number, previous: number): Delta {
  if (!current && !previous) return null;
  if (!previous) return { text: 'new', direction: 'up' };
  const change = (current - previous) / previous;
  const pct = Math.round(change * 100);
  if (pct === 0) return { text: '0%', direction: 'flat' };
  return { text: `${pct > 0 ? '+' : ''}${pct}%`, direction: pct > 0 ? 'up' : 'down' };
}

/** Change in a rate, in percentage points. */
export function rateDelta(current: number | null, previous: number | null): Delta {
  if (current == null || previous == null) return null;
  const pts = Math.round((current - previous) * 100);
  if (pts === 0) return { text: '0 pts', direction: 'flat' };
  return { text: `${pts > 0 ? '+' : ''}${pts} pts`, direction: pts > 0 ? 'up' : 'down' };
}
