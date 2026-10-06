import type { DesktopPermissionStatus } from "@/lib/desktop-host";

export const DESKTOP_PERMISSION = {
  microphone: "microphone",
  systemAudio: "systemAudio",
} as const;

export type DesktopPermissionType = (typeof DESKTOP_PERMISSION)[keyof typeof DESKTOP_PERMISSION];

export type DesktopPermissionSnapshot = {
  platform: string;
  microphone: DesktopPermissionStatus;
  systemAudio: DesktopPermissionStatus;
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

export function desktopPermissionsReady(snapshot: DesktopPermissionSnapshot): boolean {
  return snapshot.microphone === "authorized" && snapshot.systemAudio === "authorized";
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
  if (type === DESKTOP_PERMISSION.microphone) {
    return {
      enableLabel: "Microphone",
      enabledLabel: "Microphone",
      enableBody: "Vocify records your voice as You.",
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
