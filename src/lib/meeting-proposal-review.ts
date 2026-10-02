/** How memo review surfaces meeting proposals while the GET is in flight. */

export type MeetingProposalReviewInput = {
  extractionPending: boolean;
  queryFetchStatus: "fetching" | "paused" | "idle";
  queryIsPending: boolean;
  queryIsError: boolean;
  proposal: Record<string, unknown> | null;
};

export type MeetingProposalReviewSurface =
  | { kind: "pending" }
  | { kind: "read-error" }
  | { kind: "hidden" }
  | { kind: "proposal" };

export function meetingProposalReviewSurface(input: MeetingProposalReviewInput): MeetingProposalReviewSurface {
  const queryLoading =
    !input.extractionPending && input.queryIsPending && input.queryFetchStatus === "fetching";
  if (input.extractionPending || queryLoading) return { kind: "pending" };
  if (input.queryIsError && input.proposal === null) return { kind: "read-error" };
  if (input.proposal === null) return { kind: "hidden" };
  return { kind: "proposal" };
}

export type MeetingProposalPhrases = {
  save: string;
  omit: string;
  reconcile: string;
};

export function meetingProposalReadErrorView(title: string, phrases?: MeetingProposalPhrases) {
  return {
    visible: true as const,
    title,
    startsAt: null,
    save: false,
    omit: false,
    phrases,
  };
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
