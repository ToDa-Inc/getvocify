/**
 * Which Settings tabs a role can see (Lista 3, item 2; Lista 4 E6). Company-wide sections
 * (CRM, Offer/strategy, Brief/timing, Team, Billing; the playbook editor lives in Proceso de venta) are the
 * Head of Sales's (owner/admin's) call; a rep sees Calling, the shared Glossary and Usage. The
 * Head of Sales sees those too: they record and transcribe calls with their own caller-id and
 * transcription languages. Language and theme live in the avatar menu, not here.
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
  | "billing"
  | "system";

export interface SettingsTab {
  id: SettingsTabId;
  to: string;
  labelKey: string;
  /** Exact-match route (like react-router's `end`), for the settings index (CRM). */
  end?: boolean;
  /** Company-wide: Head of Sales (owner/admin) only. */
  managerOnly: boolean;
  /** Only while this company feature flag is on (e.g. the Recall meeting bot). */
  flag?: string;
  /** Only inside the desktop app (its permissions, audio check and shortcut have nothing to set on the web). */
  desktopOnly?: boolean;
}

/** Where Settings is open: the desktop app has its own System tab. */
export type SettingsHost = { desktop?: boolean };

export const SETTINGS_TABS: readonly SettingsTab[] = [
  { id: "crm", to: "/dashboard/settings", labelKey: "settingsNavCrm", end: true, managerOnly: true },
  { id: "calling", to: "/dashboard/settings/calling", labelKey: "settingsNavCalling", managerOnly: false },
  // Everyone who takes meetings, the Head of Sales included: their own calendar for the meeting bot.
  { id: "calendar", to: "/dashboard/settings/calendar", labelKey: "settingsNavCalendar", managerOnly: false, flag: "RECALL_BOT_ENABLED" },
  { id: "offer", to: "/dashboard/settings/offer", labelKey: "settingsNavOffer", managerOnly: true },
  { id: "glossary", to: "/dashboard/settings/glossary", labelKey: "settingsNavGlossary", managerOnly: false },
  { id: "brief", to: "/dashboard/settings/brief", labelKey: "settingsNavBrief", managerOnly: true },
  { id: "team", to: "/dashboard/settings/team", labelKey: "settingsNavTeam", managerOnly: true },
  { id: "usage", to: "/dashboard/settings/usage", labelKey: "settingsNavUsage", managerOnly: false },
  { id: "billing", to: "/dashboard/settings/billing", labelKey: "settingsNavBilling", managerOnly: true },
  // Everyone's own machine: permissions, audio check, shortcut. Later device settings go here too.
  { id: "system", to: "/dashboard/settings/system", labelKey: "settingsNavSystem", managerOnly: false, desktopOnly: true },
] as const;

export function visibleSettingsTabs(
  isManager: boolean,
  features: readonly string[] = [],
  host: SettingsHost = {},
): SettingsTab[] {
  return SETTINGS_TABS.filter(
    (tab) =>
      (isManager || !tab.managerOnly) &&
      (!tab.flag || features.includes(tab.flag)) &&
      (!tab.desktopOnly || host.desktop === true),
  );
}

export function firstAllowedSettingsPath(
  isManager: boolean,
  features: readonly string[] = [],
  host: SettingsHost = {},
): string {
  return visibleSettingsTabs(isManager, features, host)[0]?.to ?? "/dashboard/settings";
}

/** Whether a (possibly nested) settings pathname is one this role may land on directly. */
export function isSettingsPathAllowed(
  pathname: string,
  isManager: boolean,
  features: readonly string[] = [],
  host: SettingsHost = {},
): boolean {
  return visibleSettingsTabs(isManager, features, host).some((tab) =>
    tab.end ? pathname === tab.to : pathname === tab.to || pathname.startsWith(`${tab.to}/`),
  );
}
