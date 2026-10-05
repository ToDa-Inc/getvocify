import type { DesktopPermissionStatus } from "./desktop-host.ts";
import { desktopPlatform } from "./desktop-host.ts";

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
