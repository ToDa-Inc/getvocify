export type NavItemId = "home" | "memos" | "copilot" | "ask" | "insights" | "playbook" | "settings" | "call";

export type NavLabelKey =
  | "navHome"
  | "navToday"
  | "navMemos"
  | "navConversations"
  | "navCopilot"
  | "navAsk"
  | "navInsights"
  | "navPlaybook"
  | "navSettings"
  | "navCall";

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
const INSIGHTS: NavItem = { id: "insights", labelKey: "navInsights", path: "/dashboard/insights" };
const PLAYBOOK: NavItem = { id: "playbook", labelKey: "navPlaybook", path: "/dashboard/playbook" };
const SETTINGS: NavItem = { id: "settings", labelKey: "navSettings", path: "/dashboard/settings" };
const CALL: NavItem = { id: "call", labelKey: "navCall" };

export function isManagerRole(role?: string | null): boolean {
  return role === "owner" || role === "admin";
}

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
  // T11: the Playbook tab is for every company member (SDR, AE, General, owner/admin
  // alike), not just managers, so it sits next to Ask rather than beside Team.
  const playbook = playbookTabEnabled ? [PLAYBOOK] : [];
  if (!repWorkspace) {
    return {
      items: [HOME, MEMOS, COPILOT, ASK, ...playbook, ...(manager ? [INSIGHTS] : []), SETTINGS, CALL],
      showPlans: true,
    };
  }
  const today: NavItem = { ...HOME, labelKey: "navToday" };
  const conversations: NavItem = { ...MEMOS, labelKey: "navConversations" };
  return {
    items: manager
      ? [today, conversations, COPILOT, ASK, ...playbook, CALL, INSIGHTS, SETTINGS]
      : [today, conversations, ASK, ...playbook, CALL, SETTINGS],
    showPlans: manager,
  };
}

export function usesRepHome(company?: { repWorkspace?: boolean } | null): boolean {
  return company?.repWorkspace === true;
}
