/**
 * Which Settings tabs a role can see (Lista 3, item 2; Lista 4 E6). Company-wide sections
 * (CRM, Offer/strategy, Brief/timing, Team, Billing; the playbook editor lives in Proceso de venta) are the
 * Head of Sales's (owner/admin's) call; a rep sees Calling, the shared Glossary and Usage (the
 * personal ones, `repOnly`, are hidden for the Head of Sales). Language and theme live in the
 * avatar menu, not here.
 *
 * Pure and role-only on purpose: SettingsLayout uses it both to filter the nav and to
 * redirect a member who lands on a manager-only URL directly.
 */

export type SettingsTabId =
  | "crm"
  | "calling"
  | "calendar"
  | "offer"
  | "glossary"
  | "brief"
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
  /** Personal to a rep (their own caller-id, transcription language, memo usage): hidden for the Head of Sales, who does not call. */
  repOnly?: boolean;
  /** Only while this company feature flag is on (e.g. the Recall meeting bot). */
  flag?: string;
}

export const SETTINGS_TABS: readonly SettingsTab[] = [
  { id: "crm", to: "/dashboard/settings", labelKey: "settingsNavCrm", end: true, managerOnly: true },
  { id: "calling", to: "/dashboard/settings/calling", labelKey: "settingsNavCalling", managerOnly: false, repOnly: true },
  // Everyone who takes meetings, the Head of Sales included: their own calendar for the meeting bot.
  { id: "calendar", to: "/dashboard/settings/calendar", labelKey: "settingsNavCalendar", managerOnly: false, flag: "RECALL_BOT_ENABLED" },
  { id: "offer", to: "/dashboard/settings/offer", labelKey: "settingsNavOffer", managerOnly: true },
  { id: "glossary", to: "/dashboard/settings/glossary", labelKey: "settingsNavGlossary", managerOnly: false },
  { id: "brief", to: "/dashboard/settings/brief", labelKey: "settingsNavBrief", managerOnly: true },
  { id: "team", to: "/dashboard/settings/team", labelKey: "settingsNavTeam", managerOnly: true },
  { id: "usage", to: "/dashboard/settings/usage", labelKey: "settingsNavUsage", managerOnly: false, repOnly: true },
  { id: "billing", to: "/dashboard/settings/billing", labelKey: "settingsNavBilling", managerOnly: true },
] as const;

export function visibleSettingsTabs(isManager: boolean, features: readonly string[] = []): SettingsTab[] {
  return SETTINGS_TABS.filter(
    (tab) => (isManager ? !tab.repOnly : !tab.managerOnly) && (!tab.flag || features.includes(tab.flag)),
  );
}

export function firstAllowedSettingsPath(isManager: boolean, features: readonly string[] = []): string {
  return visibleSettingsTabs(isManager, features)[0]?.to ?? "/dashboard/settings";
}

/** Whether a (possibly nested) settings pathname is one this role may land on directly. */
export function isSettingsPathAllowed(
  pathname: string,
  isManager: boolean,
  features: readonly string[] = [],
): boolean {
  return visibleSettingsTabs(isManager, features).some((tab) =>
    tab.end ? pathname === tab.to : pathname === tab.to || pathname.startsWith(`${tab.to}/`),
  );
}
