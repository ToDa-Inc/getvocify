/** The meeting agreed on a call, shown on memo review as information only: Vocify writes nothing from it. */

export type DetectedMeeting = { startsAt: string; timezone: string | null };

/** An agreed meeting with a time; nothing for a mention without agreement or without a time. */
export function detectedMeeting(proposal: Record<string, unknown> | null | undefined): DetectedMeeting | null {
  if (!proposal || proposal.agreement !== "agreed") return null;
  const startsAt = typeof proposal.starts_at === "string" && proposal.starts_at ? proposal.starts_at : null;
  if (!startsAt) return null;
  const timezone = typeof proposal.timezone === "string" && proposal.timezone ? proposal.timezone : null;
  return { startsAt, timezone };
}

/** "mar, 29 sept · 16:00 CEST": the meeting's own clock, never the raw ISO string. */
export function meetingWhen(iso: string | null | undefined, timeZone: string | null | undefined, locale: string): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  const format = (zone: string | undefined) => {
    const day = new Intl.DateTimeFormat(locale, { weekday: "short", day: "numeric", month: "short", timeZone: zone }).format(date);
    const time = new Intl.DateTimeFormat(locale, {
      hour: "2-digit",
      minute: "2-digit",
      timeZone: zone,
      timeZoneName: zone ? "short" : undefined,
    }).format(date);
    return `${day} · ${time}`;
  };
  try {
    return format(timeZone || undefined);
  } catch {
    return format(undefined);
  }
}
