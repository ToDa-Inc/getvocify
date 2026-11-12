import type { IslandBrief } from "./desktop-call.ts";

/** A meeting from GET /calendar/upcoming: someone besides the rep (internal ones too), a call link, not over yet. */
export type UpcomingMeeting = {
  id: string;
  title: string | null;
  start_time: string;
  end_time: string | null;
  meeting_url: string;
  platform: "zoom" | "meet" | "teams" | null;
  /** Everyone but the rep, people from outside first; HubSpot names when matched. */
  people: { name: string | null; email: string; external?: boolean; hubspot_contact_id: string | null }[];
};

/** What the island shows (`shell:state` `meeting`). */
export type IslandMeeting = {
  id: string;
  who: string;
  title: string | null;
  startsAt: string;
  url: string;
  platform: UpcomingMeeting["platform"];
  brief?: IslandBrief;
};

/** The island announces a meeting a minute before it starts (as Granola does)… */
export const HEADS_UP_MS = 60_000;
/** …and keeps it while the rep may still be joining. */
export const SHOWN_AFTER_START_MS = 5 * 60_000;

function startOf(meeting: UpcomingMeeting): number {
  return Date.parse(meeting.start_time);
}

/** The meeting the island announces at `now`, soonest first; none outside its window. */
export function headsUpMeeting(meetings: UpcomingMeeting[], now: number): UpcomingMeeting | null {
  const shown = meetings.filter((m) => {
    const start = startOf(m);
    return Number.isFinite(start) && now >= start - HEADS_UP_MS && now < start + SHOWN_AFTER_START_MS;
  });
  return shown.sort((a, b) => startOf(a) - startOf(b))[0] ?? null;
}

/** When the announced meeting can next change: a heads-up starting or one ending. */
export function nextChangeAt(meetings: UpcomingMeeting[], now: number): number | null {
  const edges = meetings
    .flatMap((m) => [startOf(m) - HEADS_UP_MS, startOf(m) + SHOWN_AFTER_START_MS])
    .filter((at) => Number.isFinite(at) && at > now);
  return edges.length ? Math.min(...edges) : null;
}

/** "Marta García", "Marta García +2"; the address when there is no name, the title when nobody is listed. */
export function meetingWho(meeting: UpcomingMeeting): string {
  const [first, ...rest] = meeting.people;
  if (!first) return meeting.title ?? "";
  const name = first.name?.trim() || first.email;
  return rest.length ? `${name} +${rest.length}` : name;
}

/** Whose recent activity the island shows: the first outside person found in HubSpot (none for an internal meeting). */
export function briefContactId(meeting: UpcomingMeeting): string | null {
  return meeting.people.find((p) => p.hubspot_contact_id)?.hubspot_contact_id ?? null;
}

export function islandMeeting(meeting: UpcomingMeeting, brief: IslandBrief | null): IslandMeeting {
  return {
    id: meeting.id,
    who: meetingWho(meeting),
    title: meeting.title,
    startsAt: meeting.start_time,
    url: meeting.meeting_url,
    platform: meeting.platform,
    ...(brief ? { brief } : {}),
  };
}

/** A meeting counts as going on from this long before its start… */
const PEOPLE_BEFORE_MS = 10 * 60_000;
/** …until its end, or this long after its start when it has none. */
const PEOPLE_NO_END_MS = 60 * 60_000;

/** A person's name, or the name part of their address ("javier.ramirez@x.es" is "Javier Ramirez"). */
function personName(person: UpcomingMeeting["people"][number]): string | null {
  const name = person.name?.trim();
  if (name) return name;
  const local = person.email.split("@")[0] ?? "";
  const parts = local.split(/[._-]+/).filter((part) => /^\p{L}+$/u.test(part));
  return parts.length ? parts.map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ") : null;
}

/** Who is invited to the meeting going on at `now` (the rep left out), for naming the voices heard in it. */
export function meetingPeopleAt(meetings: UpcomingMeeting[], now: number): string[] {
  const going = meetings.filter((m) => {
    const start = startOf(m);
    const end = m.end_time ? Date.parse(m.end_time) : start + PEOPLE_NO_END_MS;
    return Number.isFinite(start) && now >= start - PEOPLE_BEFORE_MS && now < (Number.isFinite(end) ? end : start + PEOPLE_NO_END_MS);
  });
  const meeting = going.sort((a, b) => Math.abs(startOf(a) - now) - Math.abs(startOf(b) - now))[0];
  if (!meeting) return [];
  return [...new Set(meeting.people.map(personName).filter((name): name is string => Boolean(name)))];
}

/** The calendar's meetings as last loaded, so a recording can offer the people in the one it is. */
let knownMeetings: UpcomingMeeting[] = [];
export function rememberMeetings(meetings: UpcomingMeeting[]): void {
  knownMeetings = meetings;
}
export function meetingPeopleNow(now = Date.now()): string[] {
  return meetingPeopleAt(knownMeetings, now);
}
