/** Weekly adherence per rep. A week without conversations is a gap, not 0 %. Rows never sort by score. */

import type { ProductTranslations } from "./product-catalog";

export type TrendWeek = {
  week_start: string;
  state: "gap" | "unscored" | "scored";
  interactions: number;
  scored: number;
  without_playbook: number;
  without_score: number;
  met_steps: number;
  missed_steps: number;
  applicable_steps: number;
  unknown_steps: number;
  not_applicable_steps: number;
  adherence: number | null;
  coverage: number | null;
  sample_limited: boolean;
  playbook_version_ids: string[];
  new_playbook_version: boolean;
};

export type TrendPayload = {
  coverage: "complete" | "unavailable";
  timezone: string;
  weeks: { week_start: string; week_end: string; in_progress: boolean }[];
  team: { weeks: TrendWeek[] } | null;
  reps: { user_id: string; name: string; weeks: TrendWeek[] }[];
};

export type TrendRow = { key: string; name: string; weeks: TrendWeek[] };

export type TrendCopy = Pick<
  ProductTranslations,
  | "teamAdherenceOf"
  | "teamTrendNoConversations"
  | "teamTrendWithoutPlaybook"
  | "teamTrendWithoutScore"
  | "teamTrendNoEvaluable"
  | "teamTrendNewVersion"
>;

export function trendBarRatio(week: TrendWeek): number | null {
  if (week.state !== "scored" || week.adherence === null || week.applicable_steps <= 0) return null;
  return week.met_steps / week.applicable_steps;
}

export function trendCellText(week: TrendWeek, copy: TrendCopy): string {
  if (week.state === "gap") return copy.teamTrendNoConversations;
  const parts: string[] = [];
  if (week.applicable_steps > 0) {
    parts.push(
      copy.teamAdherenceOf
        .replace("{met}", String(week.met_steps))
        .replace("{applicable}", String(week.applicable_steps)),
    );
  } else if (week.scored > 0) {
    parts.push(copy.teamTrendNoEvaluable);
  }
  if (week.without_playbook > 0) {
    parts.push(copy.teamTrendWithoutPlaybook.replace("{count}", String(week.without_playbook)));
  }
  if (week.without_score > 0) {
    parts.push(copy.teamTrendWithoutScore.replace("{count}", String(week.without_score)));
  }
  if (week.new_playbook_version) parts.push(copy.teamTrendNewVersion);
  return parts.join(" · ");
}

export function trendRows(payload: TrendPayload, teamLabel: string): TrendRow[] {
  const reps = [...payload.reps]
    .sort((a, b) => a.name.localeCompare(b.name, "es"))
    .map((rep) => ({ key: rep.user_id, name: rep.name, weeks: rep.weeks }));
  return payload.team ? [{ key: "team", name: teamLabel, weeks: payload.team.weeks }, ...reps] : reps;
}

export function trendHasConversations(rows: TrendRow[]): boolean {
  return rows.some((row) => row.weeks.some((week) => week.interactions > 0));
}

export function trendSampleLimited(rows: TrendRow[]): boolean {
  return rows.some((row) => row.weeks.some((week) => week.sample_limited));
}

export function trendWeekLabel(weekStart: string, locale: string): string {
  const [year, month, day] = weekStart.split("-").map(Number);
  return new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", timeZone: "UTC" })
    .format(new Date(Date.UTC(year, month - 1, day)))
    .replace(".", "");
}
