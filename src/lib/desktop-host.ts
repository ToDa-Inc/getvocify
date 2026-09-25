/** macOS Vocify.app WKWebView — injected via desktop/macos bridge.js */
export type DesktopPermissionStatus = "authorized" | "denied" | "never_requested";

export type VocifyDesktopBridge = {
  platform: "darwin";
  systemAudio: {
    start(): Promise<{ ok: boolean; backend?: string; reason?: string }>;
    stop(): Promise<void>;
    onPcm(cb: (buffer: ArrayBuffer) => void): () => void;
    onLost?(cb: (payload: { reason?: string }) => void): () => void;
  };
  permissions: {
    status(): Promise<{
      platform: string;
      microphone: DesktopPermissionStatus;
      systemAudio: DesktopPermissionStatus;
    }>;
    request(type: "microphone" | "systemAudio"): Promise<unknown>;
    open(type: "microphone" | "systemAudio"): Promise<void>;
  };
  shell: {
    setState(state: Record<string, unknown>): void;
    resize(size: string): Promise<unknown>;
    showOverlay(): Promise<unknown>;
    hideOverlay(): Promise<unknown>;
    openExternal(url: string): Promise<{ ok?: boolean }>;
    command(name: string): void;
    onCommand(cb: (name: string) => void): () => void;
    onOverlayState?(cb: (state: Record<string, unknown>) => void): () => void;
  };
  saas: {
    request(payload: Record<string, unknown>): Promise<{
      ok: boolean;
      status?: number;
      data?: unknown;
      error?: string;
    }>;
  };
  capture: {
    begin(payload: Record<string, unknown>): Promise<unknown>;
    append(payload: Record<string, unknown>): Promise<unknown>;
    channelAbsent(payload: Record<string, unknown>): Promise<unknown>;
    pending(): Promise<unknown>;
    confirm(id: string): Promise<unknown>;
    discard(id: string): Promise<unknown>;
  };
};

declare global {
  interface Window {
    vocifyDesktop?: VocifyDesktopBridge;
    __vocifyEmit?: (channel: string, payload: unknown) => void;
  }
}

export function isDesktopHost(): boolean {
  return typeof window !== "undefined" && window.vocifyDesktop?.platform === "darwin";
}

export function getDesktopBridge(): VocifyDesktopBridge | null {
  return isDesktopHost() ? window.vocifyDesktop! : null;
}

export const DESKTOP_SHELL_EVENTS = {
  listen: "vocify-desktop:listen",
  stop: "vocify-desktop:stop",
} as const;
