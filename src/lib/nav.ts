export type NavItemId = "home" | "insights" | "process" | "coach" | "settings";

export type NavLabelKey = "navHome" | "navInsights" | "navProcess" | "navCoach" | "navSettings";

export type NavItem = {
  id: NavItemId;
  labelKey: NavLabelKey;
  path: string;
  beta?: boolean;
};

export type NavMenu = { items: NavItem[]; showPlans: boolean };

const HOME: NavItem = { id: "home", labelKey: "navHome", path: "/dashboard" };
const INSIGHTS: NavItem = { id: "insights", labelKey: "navInsights", path: "/dashboard/insights" };
const PROCESS: NavItem = { id: "process", labelKey: "navProcess", path: "/dashboard/process" };
const COACH: NavItem = { id: "coach", labelKey: "navCoach", path: "/dashboard/coach" };
const SETTINGS: NavItem = { id: "settings", labelKey: "navSettings", path: "/dashboard/settings" };

export function isManagerRole(role?: string | null): boolean {
  return role === "owner" || role === "admin";
}

// Inicio (/dashboard) is every role's home, and it lists the latest interactions ("Ver todas" opens
// /dashboard/interactions). The Head of Sales: Inicio, Equipo, Proceso de venta, Ajustes. A rep:
// Inicio, Coaching, Ajustes; the playbook they are scored against is a Coaching tab. Llamar sits
// at the top of the sidebar for reps (`topBarActions`); Ask is the floating sheet (⌘K), not a
// place. Every other route still exists, just unlinked.
export function navItemsFor({
  role,
  repWorkspace,
}: {
  role?: string | null;
  repWorkspace?: boolean;
}): NavMenu {
  if (isManagerRole(role)) {
    // Billing is the owner's: the Plans card is not shown to an admin.
    return { items: [HOME, INSIGHTS, PROCESS, SETTINGS], showPlans: role === "owner" };
  }
  return { items: [HOME, COACH, SETTINGS], showPlans: !repWorkspace };
}

/** Paths an item also owns: the full Hoy, Interacciones and a memo's detail are reached from Inicio. */
const ALSO_UNDER: Partial<Record<NavItemId, string[]>> = {
  home: ["/dashboard/today", "/dashboard/interactions", "/dashboard/memos"],
};

const within = (pathname: string, path: string) => pathname === path || pathname.startsWith(`${path}/`);

/** The sidebar item is lit on its own path and below it; Inicio on /dashboard itself and what it opens. */
export function isNavActive(pathname: string, item: Pick<NavItem, "id" | "path">): boolean {
  const also = ALSO_UNDER[item.id] ?? [];
  if (item.path === "/dashboard") return pathname === "/dashboard" || also.some((path) => within(pathname, path));
  return [item.path, ...also].some((path) => within(pathname, path));
}

/** Llamar sits in the top bar for reps; the Head of Sales doesn't dial. */
export function topBarActions(role?: string | null): boolean {
  return !isManagerRole(role);
}

export function usesRepHome(company?: { repWorkspace?: boolean } | null): boolean {
  return company?.repWorkspace === true;
}
