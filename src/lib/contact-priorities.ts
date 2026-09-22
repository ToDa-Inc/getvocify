/** How the home priority block reads a response. An error is not an empty list. */

export type PriorityCandidate = {
  id: string;
  connection_id: string;
  contact_id: string;
  deal_id?: string | null;
  reason: string;
  next_action?: string | null;
  coverage: string;
  observed_at?: string | null;
};

export type PriorityView = {
  items: PriorityCandidate[];
  coverage: string;
  title: string | null;
  action: string | null;
  contacts_url?: string | null;
  observed_at?: string | null;
};

export type PrioritySurface =
  | { kind: "loading" }
  | { kind: "error"; title: string }
  | { kind: "empty"; title: string; action: string | null; contactsUrl: string | null; observedAt: string | null }
  | { kind: "list"; items: PriorityCandidate[]; note: string | null; stale: boolean; observedAt: string | null };

export function prioritySurface(input: {
  data?: PriorityView | null;
  errorStatus?: number | null;
  isLoading: boolean;
}): PrioritySurface {
  if (input.data) {
    if (input.data.items.length === 0) {
      return {
        kind: "empty",
        title: input.data.title ?? "",
        action: input.data.action,
        contactsUrl: input.data.contacts_url ?? null,
        observedAt: input.data.observed_at ?? null,
      };
    }
    return {
      kind: "list",
      items: input.data.items,
      note: input.data.coverage === "complete" ? null : input.data.title,
      stale: Boolean(input.errorStatus),
      observedAt: input.data.observed_at ?? null,
    };
  }
  if (input.errorStatus) {
    return { kind: "error", title: "priority_update_failed" };
  }
  if (input.isLoading) return { kind: "loading" };
  return { kind: "loading" };
}
