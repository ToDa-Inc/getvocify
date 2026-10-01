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

export type RailState = "loading" | "error" | "connect" | "no_assigned" | "clear" | "partial" | "day";

/**
 * What the rail may claim, from the state `composeHome` decided. "All clear" only when Hoy says
 * so: composeHome keeps "day" while the side reads have not answered or one failed, and zero
 * counts then mean "not known yet" or "could not read", never "nothing due".
 */
export function railState(view: Pick<HomeView, "state" | "incompleteAt" | "sections">): {
  state: RailState;
  counts: RailCounts;
  incomplete: boolean;
} {
  const counts = railCounts(view);
  const incomplete = Boolean(view.incompleteAt);
  if (view.state !== "day") return { state: view.state, counts, incomplete };
  const due = counts.meetings.length + counts.needsOk + counts.tasks + counts.followups + counts.fresh + counts.calls > 0;
  if (due) return { state: "day", counts, incomplete };
  return { state: incomplete ? "partial" : "loading", counts, incomplete };
}

/** One part of Hoy that Inicio's chips open on its own (`/dashboard/today?focus=`). */
export type TodayFocus = "meetings" | "needs_ok" | "tasks" | "followups" | "new" | "calls";

/** The Hoy sections each focus shows; meetings and demos are one chip. */
const FOCUS_SECTIONS: Record<TodayFocus, readonly string[]> = {
  meetings: ["meetings", "demos"],
  needs_ok: ["needs_ok"],
  tasks: ["tasks"],
  followups: ["followups"],
  new: ["new"],
  calls: ["calls"],
};

export const TODAY_FOCUSES = Object.keys(FOCUS_SECTIONS) as TodayFocus[];

export function parseTodayFocus(raw: string | null): TodayFocus | null {
  return TODAY_FOCUSES.includes(raw as TodayFocus) ? (raw as TodayFocus) : null;
}

/** Whether a Hoy block is painted under a focus: everything without one, only its sections with one. */
export function focusShows(focus: TodayFocus | null, sectionId: string): boolean {
  return focus === null || FOCUS_SECTIONS[focus].includes(sectionId);
}

/** The chips over Hoy, in the order Hoy paints them: each part with something waiting, and how much. */
export function focusCounts(view: Pick<HomeView, "sections">): { focus: TodayFocus; count: number }[] {
  const counts = railCounts(view);
  const meetings = view.sections.reduce(
    (sum, section) => sum + (section.id === "meetings" || section.id === "demos" ? section.items.length : 0),
    0,
  );
  const all: { focus: TodayFocus; count: number }[] = [
    { focus: "meetings", count: meetings },
    { focus: "needs_ok", count: counts.needsOk },
    { focus: "tasks", count: counts.tasks },
    { focus: "followups", count: counts.followups },
    { focus: "new", count: counts.fresh },
    { focus: "calls", count: counts.calls },
  ];
  return all.filter((entry) => entry.count > 0);
}
