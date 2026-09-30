export type NavItemId = "home" | "interactions" | "insights" | "coach" | "settings";

export type NavLabelKey = "navHome" | "navInteractions" | "navInsights" | "navCoach" | "navSettings";

export type NavItem = {
  id: NavItemId;
  labelKey: NavLabelKey;
  path: string;
  beta?: boolean;
};

export type NavMenu = { items: NavItem[]; showPlans: boolean };

const HOME: NavItem = { id: "home", labelKey: "navHome", path: "/dashboard" };
const INTERACTIONS: NavItem = { id: "interactions", labelKey: "navInteractions", path: "/dashboard/interactions" };
const INSIGHTS: NavItem = { id: "insights", labelKey: "navInsights", path: "/dashboard/insights" };
const COACH: NavItem = { id: "coach", labelKey: "navCoach", path: "/dashboard/coach" };
const SETTINGS: NavItem = { id: "settings", labelKey: "navSettings", path: "/dashboard/settings" };

export function isManagerRole(role?: string | null): boolean {
  return role === "owner" || role === "admin";
}

// One home for both roles (Inicio, /dashboard). The Head of Sales: Inicio, Interacciones, Equipo,
// Ajustes. A rep: Inicio, Interacciones, Coaching, Ajustes. Llamar sits in the top bar for reps
// (`topBarActions`); Ask is the floating sheet (⌘K), not a place. Every other route still exists,
// just unlinked. `playbookTabEnabled` no longer adds an item: the rep's playbook is a Coaching tab.
export function navItemsFor({
  role,
  repWorkspace,
}: {
  role?: string | null;
  repWorkspace?: boolean;
  playbookTabEnabled?: boolean;
}): NavMenu {
  if (isManagerRole(role)) {
    // Billing is the owner's: the Plans card is not shown to an admin.
    return { items: [HOME, INTERACTIONS, INSIGHTS, SETTINGS], showPlans: role === "owner" };
  }
  return { items: [HOME, INTERACTIONS, COACH, SETTINGS], showPlans: !repWorkspace };
}

/** Paths an item also owns: a memo's detail still lives under Interacciones (MemosPage used to hold it). */
const ALSO_UNDER: Partial<Record<NavItemId, string[]>> = { interactions: ["/dashboard/memos"] };

const within = (pathname: string, path: string) => pathname === path || pathname.startsWith(`${path}/`);

/** The sidebar item is lit on its own path and below it; Inicio only on /dashboard itself. */
export function isNavActive(pathname: string, item: Pick<NavItem, "id" | "path">): boolean {
  if (item.path === "/dashboard") return pathname === "/dashboard";
  return [item.path, ...(ALSO_UNDER[item.id] ?? [])].some((path) => within(pathname, path));
}

/** Llamar sits in the top bar for reps; the Head of Sales doesn't dial. */
export function topBarActions(role?: string | null): boolean {
  return !isManagerRole(role);
}

export function usesRepHome(company?: { repWorkspace?: boolean } | null): boolean {
  return company?.repWorkspace === true;
}
