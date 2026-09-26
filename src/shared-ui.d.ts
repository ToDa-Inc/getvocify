declare module "@shared/ui/brief.js" {
  export function visibleBrief(brief: { text?: string | null; lines?: { text?: string | null }[] }): string[];
  export function briefForContact(contactId: string | null, cached: { contactId: string; brief: unknown } | null): unknown;
  export function briefOnContact(input: { objectType?: string; captureActive?: boolean; brief?: { text?: string | null; lines?: { text?: string | null }[] } | null }): string[];
  export function briefRequest(contactId: string, connectionId?: string): string;
}

declare module "@shared/ui/compose.js" {
  export type ComposeResult =
    | { ok: true; url: string }
    | { ok: false; reason: "no_email" | "no_phone" | "too_long"; fallback?: string };
  export function composeTarget(draft: {
    channel: "email" | "whatsapp";
    to?: string;
    phone?: string;
    subject?: string;
    body?: string;
    mailClient?: "default" | "gmail" | "outlook";
  }): ComposeResult;
}

declare module "@shared/ui/home.js" {
  type TodayItem = import("@/lib/today").TodayItem;
  type TodayView = import("@/lib/today").TodayView;
  type FollowupRow = import("@/lib/today").FollowupRow;
  type UpcomingRow = import("@/lib/today").UpcomingRow;
  type DoneRow = import("@/lib/today").DoneRow;
  type PriorityView = import("@/lib/contact-priorities").PriorityView;

  export const HOME_CAP: number;
  export const NEEDS_OK_VISIBLE: number;
  export const REVIEW_LIMIT: number;

  export type HomeNeedsOkRow =
    | { kind: "confirm"; item: TodayItem; action: "confirm" }
    | { kind: "confirm_group"; count: number; items: TodayItem[]; action: "expand" }
    | { kind: "followup"; memoId: string; name: string | null; subject: string | null; status: FollowupRow["status"]; action: "open" | null }
    | { kind: "review"; memoId: string; name: string | null; action: "review" };

  export type HomeSection =
    | { id: "meetings"; items: { item: TodayItem; time: string | null; past: boolean }[] }
    | { id: "needs_ok"; rows: HomeNeedsOkRow[]; shown: HomeNeedsOkRow[]; more: number }
    | { id: "calls"; items: { source: "today" | "priority"; item: TodayItem }[]; folded: number }
    | { id: "upcoming"; rows: (UpcomingRow & { inCrm: boolean; when: string | null })[] }
    | { id: "done"; rows: { kind: string; name: string | null; at: string; memoId: string | null; time: string | null }[]; count: number };

  export type HomeState = "loading" | "error" | "connect" | "no_assigned" | "clear" | "day";

  export type HomeView = {
    state: HomeState;
    canManage: boolean;
    incompleteAt: string | null;
    pulse: { calls: number; savedTo: string | null } | null;
    sections: HomeSection[];
  };

  export function composeHome(input: {
    today: TodayView | null | undefined;
    todayError: boolean;
    todayStale: boolean;
    acted: TodayItem[];
    priorities: PriorityView | null | undefined;
    followups: FollowupRow[] | null | undefined;
    reviews: { id: string; extraction?: { contactName?: string | null } | null }[] | null | undefined;
    upcoming: UpcomingRow[] | null | undefined;
    done: DoneRow[] | null | undefined;
    connected: boolean;
    role: string | null | undefined;
    crm: string | null;
    now: number;
    locale: string;
    timeZone?: string;
  }): HomeView;

  export function afterActionError(error: unknown): { forget: string | null; refetch: true } | null;
}

declare namespace JSX {
  interface IntrinsicElements {
    "v-followup": React.DetailedHTMLProps<React.HTMLAttributes<HTMLElement>, HTMLElement>;
  }
}
