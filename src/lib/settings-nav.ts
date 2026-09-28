/**
 * Which Settings tabs a role can see (Lista 3, item 2; Lista 4 E6). Company-wide sections
 * (CRM, Offer/strategy, Brief/timing, Playbooks editing, Team, Billing) are the Head of
 * Sales's (owner/admin's) call; a rep sees Calling, the shared Glossary and Usage. Interface language is not a route here - it's rendered by
 * SettingsLayout for everyone regardless of this list.
 *
 * Pure and role-only on purpose: SettingsLayout uses it both to filter the nav and to
 * redirect a member who lands on a manager-only URL directly.
 */

export type SettingsTabId =
  | "crm"
  | "calling"
  | "offer"
  | "glossary"
  | "brief"
  | "playbooks"
  | "team"
  | "usage"
  | "billing";

export interface SettingsTab {
  id: SettingsTabId;
  to: string;
  labelKey: string;
  /** Exact-match route (like react-router's `end`), for the settings index (CRM). */
  end?: boolean;
  /** Company-wide: Head of Sales (owner/admin) only. */
  managerOnly: boolean;
}

export const SETTINGS_TABS: readonly SettingsTab[] = [
  { id: "crm", to: "/dashboard/settings", labelKey: "settingsNavCrm", end: true, managerOnly: true },
  { id: "calling", to: "/dashboard/settings/calling", labelKey: "settingsNavCalling", managerOnly: false },
  { id: "offer", to: "/dashboard/settings/offer", labelKey: "settingsNavOffer", managerOnly: true },
  { id: "glossary", to: "/dashboard/settings/glossary", labelKey: "settingsNavGlossary", managerOnly: false },
  { id: "brief", to: "/dashboard/settings/brief", labelKey: "settingsNavBrief", managerOnly: true },
  // "playbooks" moved to the Head of Sales' Proceso de venta page (/dashboard/process);
  // /dashboard/settings/playbooks redirects there.
  { id: "team", to: "/dashboard/settings/team", labelKey: "settingsNavTeam", managerOnly: true },
  { id: "usage", to: "/dashboard/settings/usage", labelKey: "settingsNavUsage", managerOnly: false },
  { id: "billing", to: "/dashboard/settings/billing", labelKey: "settingsNavBilling", managerOnly: true },
] as const;

export function visibleSettingsTabs(isManager: boolean): SettingsTab[] {
  return SETTINGS_TABS.filter((tab) => isManager || !tab.managerOnly);
}

export function firstAllowedSettingsPath(isManager: boolean): string {
  return visibleSettingsTabs(isManager)[0]?.to ?? "/dashboard/settings";
}

/** Whether a (possibly nested) settings pathname is one this role may land on directly. */
export function isSettingsPathAllowed(pathname: string, isManager: boolean): boolean {
  return visibleSettingsTabs(isManager).some((tab) =>
    tab.end ? pathname === tab.to : pathname === tab.to || pathname.startsWith(`${tab.to}/`),
  );
}
