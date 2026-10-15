/**
 * Which Settings tabs a role can see (Lista 3, item 2; Lista 4 E6). Company-wide sections
 * (CRM, Offer/strategy, Team, Billing; the playbook editor lives in Proceso de venta) are the
 * Head of Sales's (owner/admin's) call; everyone sees their own Preferences (call languages, glossary,
 * summaries, reports), Calling and Usage. The Head of Sales sees those too: they record and transcribe
 * calls with their own caller-id and transcription languages. Language and theme live in the avatar menu.
 *
 * Pure and role-only on purpose: SettingsLayout uses it both to filter the nav and to
 * redirect a member who lands on a manager-only URL directly.
 */

export type SettingsTabId =
  | "preferences"
  | "calling"
  | "calendar"
  | "agents"
  | "system"
  | "usage"
  | "crm"
  | "offer"
  | "team"
  | "billing";

/** The rail has two blocks, like Granola's: what is mine, and what is the company's (Head of Sales). */
export type SettingsGroup = "personal" | "workspace";

export interface SettingsTab {
  id: SettingsTabId;
  to: string;
  labelKey: string;
  group: SettingsGroup;
  /** Company-wide: Head of Sales (owner/admin) only. */
  managerOnly: boolean;
  /** Only while this company feature flag is on (e.g. the Recall meeting bot). */
  flag?: string;
  /** Only inside the desktop app (its permissions, audio check and shortcut have nothing to set on the web). */
  desktopOnly?: boolean;
}

/** Where Settings is open: the desktop app has its own System tab. */
export type SettingsHost = { desktop?: boolean };

/** The bare `/dashboard/settings`: the OAuth return of a CRM lands here with its query, so it is never a tab. */
export const SETTINGS_ROOT = "/dashboard/settings";

export const SETTINGS_TABS: readonly SettingsTab[] = [
  // Everyone's own preferences: call languages, glossary, after-call summaries, reports, shortcut, island.
  { id: "preferences", to: "/dashboard/settings/preferences", labelKey: "settingsNavPreferences", group: "personal", managerOnly: false },
  { id: "calling", to: "/dashboard/settings/calling", labelKey: "settingsNavCalling", group: "personal", managerOnly: false },
  // Everyone who takes meetings, the Head of Sales included: their own calendar for the meeting bot.
  { id: "calendar", to: "/dashboard/settings/calendar", labelKey: "settingsNavCalendar", group: "personal", managerOnly: false, flag: "RECALL_BOT_ENABLED" },
  // Everyone's own API key and connected apps; owners and admins also get the workspace switches there.
  { id: "agents", to: "/dashboard/settings/agents", labelKey: "settingsNavAgents", group: "personal", managerOnly: false },
  // Everyone's own machine: permissions and audio check.
  { id: "system", to: "/dashboard/settings/system", labelKey: "settingsNavSystem", group: "personal", managerOnly: false, desktopOnly: true },
  { id: "usage", to: "/dashboard/settings/usage", labelKey: "settingsNavUsage", group: "personal", managerOnly: false },
  { id: "crm", to: "/dashboard/settings/crm", labelKey: "settingsNavCrm", group: "workspace", managerOnly: true },
  { id: "offer", to: "/dashboard/settings/offer", labelKey: "settingsNavOffer", group: "workspace", managerOnly: true },
  { id: "team", to: "/dashboard/settings/team", labelKey: "settingsNavTeam", group: "workspace", managerOnly: true },
  { id: "billing", to: "/dashboard/settings/billing", labelKey: "settingsNavBilling", group: "workspace", managerOnly: true },
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
  return visibleSettingsTabs(isManager, features, host)[0]?.to ?? SETTINGS_ROOT;
}

/** Whether a (possibly nested) settings pathname is one this role may land on directly. */
export function isSettingsPathAllowed(
  pathname: string,
  isManager: boolean,
  features: readonly string[] = [],
  host: SettingsHost = {},
): boolean {
  return visibleSettingsTabs(isManager, features, host).some((tab) =>
    pathname === tab.to || pathname.startsWith(`${tab.to}/`),
  );
}
