declare module "@shared/ui/brief.js" {
  export function visibleBrief(brief: { text?: string | null; lines?: { text?: string | null }[] }): string[];
  export function briefForContact(contactId: string | null, cached: { contactId: string; brief: unknown } | null): unknown;
  export function briefOnContact(input: { objectType?: string; captureActive?: boolean; brief?: { text?: string | null; lines?: { text?: string | null }[] } | null }): string[];
  export function briefRequest(contactId: string, connectionId?: string): string;
  export const BRIEF_LOADING: string;
  export const BRIEF_MAX_LINES: number;

  export type BriefPayload = {
    status?: string;
    text?: string | null;
    notice?: string | null;
    label?: string | null;
    lines?: { type?: string; text?: string | null; source?: string | null }[];
  };
  export type BriefRow = { text: string; playbook: boolean };
  export type BriefRows = { notice: string | null; rows: BriefRow[]; label: string | null };
  export type PanelBrief = BriefRows & { state: "none" | "loading" | "failed" | "ready" };

  export function briefRows(brief: BriefPayload | null | undefined): BriefRows;
  export function panelBrief(input: {
    contactId: string | null;
    cache: { contactId: string; brief: BriefPayload } | null;
    flightContactId: string | null;
    failedContactId?: string | null;
  }): PanelBrief;
}

declare module "@shared/ui/queue.js" {
  export type QueueAction = "call" | "skip" | "exit" | "reviewed" | "next" | "prev";
  export const HOME_KEYS: Record<string, Record<string, QueueAction>>;
  export const QUEUE_KEYS: Record<string, Record<string, QueueAction>>;
  export function queueKeyAction(
    mode: string,
    key: string,
    event?: { metaKey?: boolean; ctrlKey?: boolean; altKey?: boolean; target?: EventTarget | null },
    keys?: Record<string, Record<string, QueueAction>>,
  ): QueueAction | null;
}

declare module "@shared/ui/today-card.js" {
  export type Leaving<T> = { entry: T; leaving: boolean };
  export function exitMotion(reducedMotion: boolean): { opacity: boolean; transform: boolean; height: boolean; measureHeight?: boolean };
  export function retainLeaving<T>(previous: Leaving<T>[], next: T[], keyOf: (entry: T) => string): Leaving<T>[];
  export function dropLeaving<T>(rows: Leaving<T>[], key: string, keyOf: (entry: T) => string): Leaving<T>[];
  export function settleRowHeights(
    beforeHeight: number,
    afterHeight: number,
    reducedMotion?: boolean,
  ): { animate: boolean; fromHeight: number; toHeight: number };
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
  export const FOLLOWUP_POLL_MS: number;
  export const FOLLOWUP_POLL_FOR_MS: number;
  export const HOME_WIDE_PX: number;

  export type HomeNeedsOkRow =
    | { kind: "confirm"; item: TodayItem; action: "confirm" }
    | { kind: "confirm_group"; count: number; items: TodayItem[]; action: "expand" }
    | { kind: "followup"; memoId: string; contactId: string | null; name: string | null; subject: string | null; status: FollowupRow["status"]; action: "open" | null }
    | { kind: "review"; memoId: string; contactId: string | null; name: string | null; action: "review" };

  export type HomeSection =
    | { id: "meetings"; items: { item: TodayItem; time: string | null; past: boolean }[] }
    | { id: "needs_ok"; rows: HomeNeedsOkRow[]; shown: HomeNeedsOkRow[]; more: number }
    | { id: "calls"; items: { source: "today" | "priority"; item: TodayItem }[] }
    | { id: "upcoming"; rows: (UpcomingRow & { inCrm: boolean; when: string | null })[] }
    | { id: "done"; rows: { kind: string; name: string | null; contactId: string | null; at: string; memoId: string | null; time: string | null }[]; count: number };

  export type HomeState = "loading" | "error" | "connect" | "no_assigned" | "clear" | "day";

  export type HomeView = {
    state: HomeState;
    canManage: boolean;
    incompleteAt: string | null;
    pulse: { calls: number; savedTo: string | null } | null;
    folded: { count: number; after: "meetings" | "needs_ok" | "calls" | null } | null;
    sections: HomeSection[];
  };

  /** `undefined` = still loading, `null` = the read failed. */
  export function composeHome(input: {
    today: TodayView | null | undefined;
    todayStale: boolean;
    acted: TodayItem[];
    priorities: PriorityView | null | undefined;
    followups: FollowupRow[] | null | undefined;
    reviews: { id: string; extraction?: { contactName?: string | null } | null }[] | null | undefined;
    upcoming: UpcomingRow[] | null | undefined;
    done: DoneRow[] | null | undefined;
    connected: boolean | undefined;
    role: string | null | undefined;
    crm: string | null;
    now: number;
    locale: string;
    timeZone?: string;
  }): HomeView;

  export function followupPoll(
    rows: FollowupRow[] | null | undefined,
    since: number | null,
    now: number,
  ): { interval: number | false; since: number | null };

  export function afterActionError(error: unknown): { forget: string | null; refetch: true } | null;

  export type HomeRow =
    | { key: string; kind: "meeting"; contactId: string | null; name: string | null; item: TodayItem; time: string | null }
    | { key: string; kind: "confirm"; contactId: string | null; name: string | null; item: TodayItem }
    | { key: string; kind: "followup"; contactId: string | null; name: string | null; entry: Extract<HomeNeedsOkRow, { kind: "followup" }> }
    | { key: string; kind: "review"; contactId: string | null; name: string | null; entry: Extract<HomeNeedsOkRow, { kind: "review" }> }
    | { key: string; kind: "call"; source: "today" | "priority"; contactId: string | null; name: string | null; item: TodayItem };

  export type HomeSelection = {
    mode: string;
    items: string[];
    index?: number;
    touched: boolean;
    memoId?: string;
    callSid?: string | null;
    lastOutcome?: string;
  };
  export type HomeSelectionEvent =
    | { type: "rows"; rows: HomeRow[]; wide: boolean }
    | { type: "select"; key: string }
    | { type: "next" }
    | { type: "prev" }
    | { type: "skip" }
    | { type: "exit" }
    | { type: "call" }
    | {
        type: "call_ended";
        memoId?: string | null;
        screeningOutcome?: string | null;
        callStatus?: "failed";
        callSid?: string | null;
      }
    | { type: "reviewed" };
  export type HomeOrder = Record<string, string[]>;

  export const initialHomeSelection: HomeSelection;
  export function itemKey(item: TodayItem): string;
  export function needsOkKey(entry: HomeNeedsOkRow): string;
  export function homeRows(view: HomeView, open?: { needsOkOpen?: boolean; groupOpen?: boolean }): HomeRow[];
  export function homeSelection(state: HomeSelection, event: HomeSelectionEvent): HomeSelection;
  export function homeSelectionLocked(state: HomeSelection): boolean;
  export function homeSelectionInReview(state: HomeSelection): boolean;
  export function selectedRow(state: HomeSelection, rows: HomeRow[]): HomeRow | null;
  export function holdOrder(order: HomeOrder | null, view: HomeView): { view: HomeView; order: HomeOrder };
  export function snoozeUntil(now: number, timeZone?: string): string;
}

declare namespace JSX {
  interface IntrinsicElements {
    "v-followup": React.DetailedHTMLProps<React.HTMLAttributes<HTMLElement>, HTMLElement>;
  }
}
