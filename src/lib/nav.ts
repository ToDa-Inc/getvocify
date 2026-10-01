export type NavItemId =
  | "home"
  | "insights"
  | "coach"
  | "playbook"
  | "process"
  | "settings";

export type NavLabelKey =
  | "navHome"
  | "navInsights"
  | "navCoach"
  | "navPlaybook"
  | "navProcess"
  | "navSettings";

export type NavItem = {
  id: NavItemId;
  labelKey: NavLabelKey;
  path: string;
  beta?: boolean;
};

export type NavMenu = { items: NavItem[]; showPlans: boolean };

const HOME: NavItem = { id: "home", labelKey: "navHome", path: "/dashboard" };
const INSIGHTS: NavItem = { id: "insights", labelKey: "navInsights", path: "/dashboard/insights" };
const COACH: NavItem = { id: "coach", labelKey: "navCoach", path: "/dashboard/coach" };
const PLAYBOOK: NavItem = { id: "playbook", labelKey: "navPlaybook", path: "/dashboard/playbook" };
const SETTINGS: NavItem = { id: "settings", labelKey: "navSettings", path: "/dashboard/settings" };
const PROCESS: NavItem = { id: "process", labelKey: "navProcess", path: "/dashboard/process" };

export function isManagerRole(role?: string | null): boolean {
  return role === "owner" || role === "admin";
}

// Inicio (/dashboard) is every role's home. A member (Llamadas, Reuniones, General) has
// Inicio, Playbook, Coaching and Ajustes; their full Hoy is /dashboard/today, reached from
// Inicio's rail. The Admin/Owner keeps Equipo and Proceso de venta, with Inicio added.
// Interacciones is Inicio's latest list for every role ("Ver todas" opens /dashboard/interactions).
// Ask and Llamar sit in the top bar for every role.
// Every other route still exists, just unlinked.
export function navItemsFor({
  role,
  repWorkspace,
  playbookTabEnabled,
}: {
  role?: string | null;
  repWorkspace?: boolean;
  playbookTabEnabled?: boolean;
}): NavMenu {
  if (isManagerRole(role)) {
    // Billing is the owner's: the Plans card is not shown to an admin.
    return { items: [HOME, INSIGHTS, PROCESS, SETTINGS], showPlans: role === "owner" };
  }
  // T11: the Playbook tab is for every company member.
  const playbook = playbookTabEnabled ? [PLAYBOOK] : [];
  return { items: [HOME, ...playbook, COACH, SETTINGS], showPlans: !repWorkspace };
}

/** Paths an item also owns: the full Hoy, Interacciones and a memo's detail are reached from Inicio. */
const ALSO_UNDER: Partial<Record<NavItemId, string[]>> = {
  home: ["/dashboard/today", "/dashboard/interactions", "/dashboard/memos"],
};

const within = (pathname: string, path: string) => pathname === path || pathname.startsWith(`${path}/`);

/** The sidebar item is lit on its own path and below it; Inicio only on /dashboard itself and what it opens. */
export function isNavActive(pathname: string, item: Pick<NavItem, "id" | "path">): boolean {
  const also = ALSO_UNDER[item.id] ?? [];
  if (item.path === "/dashboard") return pathname === "/dashboard" || also.some((path) => within(pathname, path));
  return [item.path, ...also].some((path) => within(pathname, path));
}

export function usesRepHome(company?: { repWorkspace?: boolean } | null): boolean {
  return company?.repWorkspace === true;
}
