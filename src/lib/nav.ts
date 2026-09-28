export type NavItemId = "home" | "memos" | "copilot" | "ask" | "insights" | "coach" | "playbook" | "process" | "settings" | "call";

export type NavLabelKey =
  | "navHome"
  | "navToday"
  | "navMemos"
  | "navConversations"
  | "navRecordings"
  | "navCopilot"
  | "navAsk"
  | "navCall"
  | "navInsights"
  | "navCoach"
  | "navPlaybook"
  | "navSummary"
  | "navProcess"
  | "navSettings";

export type NavItem = {
  id: NavItemId;
  labelKey: NavLabelKey;
  path?: string;
  beta?: boolean;
};

export type NavMenu = { items: NavItem[]; showPlans: boolean };

const HOME: NavItem = { id: "home", labelKey: "navHome", path: "/dashboard" };
const MEMOS: NavItem = { id: "memos", labelKey: "navMemos", path: "/dashboard/memos" };
const COPILOT: NavItem = { id: "copilot", labelKey: "navCopilot", path: "/dashboard/copilot", beta: true };
const ASK: NavItem = { id: "ask", labelKey: "navAsk", path: "/dashboard/ask" };
const CALL: NavItem = { id: "call", labelKey: "navCall" };
const INSIGHTS: NavItem = { id: "insights", labelKey: "navInsights", path: "/dashboard/insights" };
const COACH: NavItem = { id: "coach", labelKey: "navCoach", path: "/dashboard/coach" };
const PLAYBOOK: NavItem = { id: "playbook", labelKey: "navPlaybook", path: "/dashboard/playbook" };
const SETTINGS: NavItem = { id: "settings", labelKey: "navSettings", path: "/dashboard/settings" };
// Head of Sales (docs/features/HEAD_OF_SALES_DASHBOARD_PLAN.md §2): Resumen is the manager's /dashboard.
const SUMMARY: NavItem = { ...HOME, labelKey: "navSummary" };
const PROCESS: NavItem = { id: "process", labelKey: "navProcess", path: "/dashboard/process" };

export function isManagerRole(role?: string | null): boolean {
  return role === "owner" || role === "admin";
}

// Lista 4 E1–E5 apply to reps (SDR/AE/General) only: their sidebar is only their places -
// no Copilot link (its route stays), Ask and Call live in the top bar (DashboardLayout,
// `topBarActions`), Recordings, and Coach where a manager gets Team.
// The Head of Sales (owner/admin) does not call: their sidebar is the plan's four places -
// Resumen, Equipo, Proceso de venta, Ajustes - and Ask (the manager chat) sits in the top
// bar without Call (`managerTopBarAsk`). Every other route still exists, just unlinked.
export function navItemsFor({
  role,
  repWorkspace,
  playbookTabEnabled,
}: {
  role?: string | null;
  repWorkspace?: boolean;
  playbookTabEnabled?: boolean;
}): NavMenu {
  const manager = isManagerRole(role);
  // T11: the Playbook tab is for every company member (SDR, AE, General, owner/admin alike).
  const playbook = playbookTabEnabled ? [PLAYBOOK] : [];
  if (manager) {
    // Billing is the owner's: the Plans card is not shown to an admin.
    return { items: [SUMMARY, INSIGHTS, PROCESS, SETTINGS], showPlans: role === "owner" };
  }
  const home: NavItem = repWorkspace ? { ...HOME, labelKey: "navToday" } : HOME;
  const recordings: NavItem = { ...MEMOS, labelKey: "navRecordings" };
  return {
    items: [home, recordings, ...playbook, COACH, SETTINGS],
    showPlans: !repWorkspace,
  };
}

/** Lista 4 E3: Ask and Call sit in the top bar for reps. */
export function topBarActions(role?: string | null): boolean {
  return !isManagerRole(role);
}

/** Head of Sales: Ask (manager chat) in the top bar, and no Call - they don't dial. */
export function managerTopBarAsk(role?: string | null): boolean {
  return isManagerRole(role);
}

export function usesRepHome(company?: { repWorkspace?: boolean } | null): boolean {
  return company?.repWorkspace === true;
}
