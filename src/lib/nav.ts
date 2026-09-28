export type NavItemId = "home" | "memos" | "insights" | "coach" | "playbook" | "settings";

export type NavLabelKey =
  | "navHome"
  | "navToday"
  | "navMemos"
  | "navConversations"
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
const INSIGHTS: NavItem = { id: "insights", labelKey: "navInsights", path: "/dashboard/insights" };
const COACH: NavItem = { id: "coach", labelKey: "navCoach", path: "/dashboard/coach" };
const PLAYBOOK: NavItem = { id: "playbook", labelKey: "navPlaybook", path: "/dashboard/playbook" };
const SETTINGS: NavItem = { id: "settings", labelKey: "navSettings", path: "/dashboard/settings" };

export function isManagerRole(role?: string | null): boolean {
  return role === "owner" || role === "admin";
}

// Lista 4 E1–E5: the sidebar is only the rep's places. Copilot has no link (its route
// stays), Ask and Call live in the top bar, and a rep gets Coach where a manager gets Team.
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
  const home: NavItem = repWorkspace ? { ...HOME, labelKey: "navToday" } : HOME;
  const recordings: NavItem = repWorkspace ? { ...MEMOS, labelKey: "navConversations" } : MEMOS;
  return {
    items: [home, recordings, ...playbook, manager ? INSIGHTS : COACH, SETTINGS],
    showPlans: repWorkspace ? manager : true,
  };
}

export function usesRepHome(company?: { repWorkspace?: boolean } | null): boolean {
  return company?.repWorkspace === true;
}
