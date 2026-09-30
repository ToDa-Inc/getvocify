/**
 * Inicio's rep rail: Hoy condensed to what decides the next click. It reads the view `composeHome`
 * already built for /dashboard/today, so every number here is exactly what Hoy paints: the
 * sections a role gets, "Falta tu OK" from confirmations + follow-ups + calls to review, the caps.
 */
import type { HomeSection, HomeView } from "@shared/ui/home.js";

export const RAIL_MEETINGS = 3;

export type RailMeeting = Extract<HomeSection, { id: "meetings" | "demos" }>["items"][number];

export type RailCounts = {
  meetings: RailMeeting[];
  needsOk: number;
  tasks: number;
  followups: number;
  /** Nuevos. */
  fresh: number;
  /** "A quién llamar": the list a rep gets when Hoy is not split in sections. */
  calls: number;
};

function startOf(entry: RailMeeting): number {
  const at = entry.item.precision !== "date" && entry.item.due_at ? Date.parse(entry.item.due_at) : NaN;
  return Number.isNaN(at) ? Infinity : at;
}

/** Still to come first, by start time; one without a time after the timed ones; started ones last. */
function soonest(a: RailMeeting, b: RailMeeting): number {
  return Number(a.past) - Number(b.past) || startOf(a) - startOf(b);
}

export function railCounts(view: Pick<HomeView, "sections">): RailCounts {
  const out: RailCounts = { meetings: [], needsOk: 0, tasks: 0, followups: 0, fresh: 0, calls: 0 };
  const meetings: RailMeeting[] = [];
  for (const section of view.sections) {
    switch (section.id) {
      case "meetings":
      case "demos":
        meetings.push(...section.items);
        break;
      case "needs_ok":
        out.needsOk = section.rows.reduce((sum, row) => sum + (row.kind === "confirm_group" ? row.count : 1), 0);
        break;
      case "tasks":
        out.tasks = section.items.length;
        break;
      case "followups":
        out.followups = section.items.length;
        break;
      case "new":
        out.fresh = section.items.length;
        break;
      case "calls":
        out.calls = section.items.length;
        break;
    }
  }
  out.meetings = meetings.sort(soonest).slice(0, RAIL_MEETINGS);
  return out;
}
