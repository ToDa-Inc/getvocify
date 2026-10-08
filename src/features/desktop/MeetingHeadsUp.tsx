import { useEffect } from "react";
import { useAuth } from "@/features/auth";
import { calendarApi } from "@/lib/api/calendar";
import { islandBrief, type IslandBrief } from "@/lib/desktop-call";
import { getDesktopBridge } from "@/lib/desktop-host";
import { briefContactId, headsUpMeeting, islandMeeting, nextChangeAt, type UpcomingMeeting } from "@/lib/meeting-heads-up";
import { api } from "@/shared/lib/api-client";

/** How often the rep's next meetings are read: every minute, so a meeting added just before it starts still gets
 * its heads-up (the backend reads its stored copy; it asks Recall again at most every 5 minutes, and Recall's
 * calendar webhook keeps the copy current in between). */
const REFRESH_MS = 60_000;

/**
 * A minute before a meeting (with clients or internal), the island says who it is with and, for a
 * client in HubSpot, what happened with them lately, with Join and Record (`shell:state` `meeting`). Desktop host only;
 * nothing without a connected calendar. A recording made then is linked to the meeting by the
 * backend, from when it started.
 */
export function MeetingHeadsUp() {
  const { user } = useAuth();
  const calendarOn = Boolean(user?.company?.features?.includes("RECALL_BOT_ENABLED"));

  useEffect(() => {
    const bridge = getDesktopBridge();
    if (!bridge || !calendarOn) return;
    let meetings: UpcomingMeeting[] = [];
    let shownId: string | null = null;
    const briefs = new Map<string, IslandBrief | null>();
    let timer: number | null = null;
    let stopped = false;

    const send = (meeting: UpcomingMeeting | null) => {
      if (stopped) return;
      shownId = meeting?.id ?? null;
      bridge.shell.setState({ meeting: meeting ? islandMeeting(meeting, briefs.get(meeting.id) ?? null) : null });
    };

    const loadBrief = (meeting: UpcomingMeeting) => {
      const contactId = briefContactId(meeting);
      if (!contactId || briefs.has(meeting.id)) return;
      briefs.set(meeting.id, { state: "loading" });
      api
        .get<Parameters<typeof islandBrief>[0]>(`/contacts/${encodeURIComponent(contactId)}/recent-activity?connection_id=hubspot`)
        .then((activity) => islandBrief(activity))
        .catch(() => null)
        .then((brief) => {
          briefs.set(meeting.id, brief);
          if (shownId === meeting.id) send(meeting);
        });
    };

    // Shows what is due now, then sleeps until the next heads-up starts or ends.
    const update = () => {
      if (timer !== null) window.clearTimeout(timer);
      const now = Date.now();
      const due = headsUpMeeting(meetings, now);
      if (due) loadBrief(due);
      if (due || shownId) send(due);
      const next = nextChangeAt(meetings, now);
      timer = next === null ? null : window.setTimeout(update, Math.max(next - now, 250));
    };

    const refresh = () => {
      if (!api.getToken()) return;
      calendarApi
        .upcoming()
        .then((next) => {
          meetings = next;
          update();
        })
        .catch(() => {
          // Calendar unreachable: keep what we had; the next refresh tries again.
        });
    };

    refresh();
    const every = window.setInterval(refresh, REFRESH_MS);
    return () => {
      stopped = true;
      window.clearInterval(every);
      if (timer !== null) window.clearTimeout(timer);
      bridge.shell.setState({ meeting: null });
    };
  }, [calendarOn]);

  return null;
}
