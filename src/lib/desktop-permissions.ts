import type { DesktopPermissionStatus } from "./desktop-host.ts";
import { desktopPlatform } from "./desktop-host.ts";

export const DESKTOP_PERMISSION = {
  microphone: "microphone",
  systemAudio: "systemAudio",
  /** Reading the CRM tab in the rep's browsers, so the island can call the contact on screen. */
  crmTabs: "crmTabs",
} as const;

/** `unavailable`: no supported browser is open, so macOS has nothing to ask about yet. */
export type CrmTabsStatus = DesktopPermissionStatus | "unavailable";

export type DesktopPermissionType = (typeof DESKTOP_PERMISSION)[keyof typeof DESKTOP_PERMISSION];

export type DesktopPermissionSnapshot = {
  platform: string;
  microphone: DesktopPermissionStatus;
  systemAudio: DesktopPermissionStatus;
  /** Missing when the Mac build cannot call yet. */
  crmTabs?: CrmTabsStatus;
  signing?: "adhoc" | "signed";
  signingAuthority?: string;
  systemAudioError?: string;
};

export function normalizePermissionStatus(raw: unknown): DesktopPermissionStatus {
  const value = String(raw ?? "").toLowerCase();
  if (value === "granted" || value === "authorized") return "authorized";
  if (value === "denied" || value === "restricted") return "denied";
  return "never_requested";
}

export function normalizeCrmTabsStatus(raw: unknown): CrmTabsStatus | undefined {
  if (raw == null) return undefined;
  return String(raw).toLowerCase() === "unavailable" ? "unavailable" : normalizePermissionStatus(raw);
}

/** Optional, never blocking: the rep has not answered yet (or has no browser open to ask about). */
export function crmTabsToAsk(snapshot: DesktopPermissionSnapshot): boolean {
  return snapshot.crmTabs === "never_requested" || snapshot.crmTabs === "unavailable";
}

export function desktopPermissionsReady(snapshot: DesktopPermissionSnapshot): boolean {
  const micReady = snapshot.microphone === "authorized";
  // Windows: systemAudio is always available, only microphone matters
  if (snapshot.platform === "win32") return micReady;
  // macOS: both mic and system audio must be authorized
  return micReady && snapshot.systemAudio === "authorized";
}

export function desktopPermissionsBlocker(
  snapshot: DesktopPermissionSnapshot,
): "permissions" | "none" {
  if (!desktopPermissionsReady(snapshot)) return "permissions";
  return "none";
}

export function permissionAction(
  status: DesktopPermissionStatus,
  { deniedOpensSettings = true } = {},
): "none" | "request" | "open_settings" {
  if (status === "authorized") return "none";
  if (status === "denied" && deniedOpensSettings) return "open_settings";
  return "request";
}

export function permissionCopy(type: DesktopPermissionType): {
  enableLabel: string;
  enabledLabel: string;
  enableBody: string;
  enabledBody: string;
} {
  if (type === DESKTOP_PERMISSION.crmTabs) {
    return {
      enableLabel: "Read your CRM tab",
      enabledLabel: "CRM tab",
      enableBody: "So Vocify can call the contact you have open.",
      enabledBody: "Ready.",
    };
  }

  const platform = desktopPlatform();

  if (type === DESKTOP_PERMISSION.microphone) {
    return {
      enableLabel: "Microphone",
      enabledLabel: "Microphone",
      enableBody: "Vocify records your voice as You.",
      enabledBody: "Ready.",
    };
  }

  // System audio copy varies by platform
  if (platform === "win32") {
    return {
      enableLabel: "Meeting audio",
      enabledLabel: "Meeting audio",
      enableBody: "So Vocify hears Zoom, Meet, and Teams as Them. Your screen is not saved.",
      enabledBody: "Ready.",
    };
  }

  return {
    enableLabel: "System audio",
    enabledLabel: "System audio",
    enableBody: "So Vocify hears Zoom, Meet, and Teams as Them. Your screen is not saved.",
    enabledBody: "Ready.",
  };
}

/**
 * What to tell someone whose system audio is still off. macOS applies Screen & System Audio
 * Recording only after a restart, so once they've been to Settings the next step is a relaunch.
 * Still off after relaunching for it means the listed Vocify belongs to another build: re-add it.
 */
export function systemAudioHint(
  status: DesktopPermissionStatus,
  { asked, relaunched }: { asked: boolean; relaunched: boolean },
): "none" | "relaunch" | "stuck" {
  if (status === "authorized") return "none";
  if (relaunched) return "stuck";
  if (asked) return "relaunch";
  return "none";
}
