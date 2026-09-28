/**
 * Which Settings tabs a role can see (Lista 3, item 2). Company-wide sections (CRM,
 * Offer/strategy, Glossary, Playbooks editing, Team, Usage, Billing) are the Head of
 * Sales's (owner/admin's) call; a rep only ever sees their own personal settings
 * (Calling, Brief/timing). Interface language is not a route here - it's rendered by
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
  { id: "glossary", to: "/dashboard/settings/glossary", labelKey: "settingsNavGlossary", managerOnly: true },
  { id: "brief", to: "/dashboard/settings/brief", labelKey: "settingsNavBrief", managerOnly: false },
  { id: "playbooks", to: "/dashboard/settings/playbooks", labelKey: "settingsNavPlaybooks", managerOnly: true },
  { id: "team", to: "/dashboard/settings/team", labelKey: "settingsNavTeam", managerOnly: true },
  { id: "usage", to: "/dashboard/settings/usage", labelKey: "settingsNavUsage", managerOnly: true },
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
