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
    enableBody:
      "Under Screen & System Audio Recording so Vocify hears Zoom, Meet, and Teams as Them. Your screen is not saved.",
    enabledBody: "Ready.",
  };
}
