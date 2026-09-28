export type NavItemId = "home" | "memos" | "copilot" | "ask" | "insights" | "coach" | "playbook" | "settings" | "call";

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

export function isManagerRole(role?: string | null): boolean {
  return role === "owner" || role === "admin";
}

// Lista 4 E1–E5 apply to reps (SDR/AE/General) only: their sidebar is only their places -
// no Copilot link (its route stays), Ask and Call live in the top bar (DashboardLayout,
// `topBarActions`), Recordings, and Coach where a manager gets Team. The Head of Sales'
// menu is left exactly as it was: it is being redesigned separately.
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
    if (!repWorkspace) {
      return { items: [HOME, MEMOS, COPILOT, ASK, ...playbook, INSIGHTS, SETTINGS, CALL], showPlans: true };
    }
    const today: NavItem = { ...HOME, labelKey: "navToday" };
    const conversations: NavItem = { ...MEMOS, labelKey: "navConversations" };
    return { items: [today, conversations, COPILOT, ASK, ...playbook, CALL, INSIGHTS, SETTINGS], showPlans: true };
  }
  const home: NavItem = repWorkspace ? { ...HOME, labelKey: "navToday" } : HOME;
  const recordings: NavItem = { ...MEMOS, labelKey: "navRecordings" };
  return {
    items: [home, recordings, ...playbook, COACH, SETTINGS],
    showPlans: !repWorkspace,
  };
}

/** Lista 4 E3: Ask and Call sit in the top bar for reps; a manager keeps them in the sidebar. */
export function topBarActions(role?: string | null): boolean {
  return !isManagerRole(role);
}

export function usesRepHome(company?: { repWorkspace?: boolean } | null): boolean {
  return company?.repWorkspace === true;
}
