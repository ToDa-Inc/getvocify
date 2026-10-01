/** The Vocify Mac app's WKWebView bridge, injected by the native shell's bridge.js. */
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
      signing?: "adhoc" | "signed";
      signingAuthority?: string;
      systemAudioError?: string;
    }>;
    request(type: "microphone" | "systemAudio"): Promise<unknown>;
    open(type: "microphone" | "systemAudio"): Promise<void>;
    guide?(type: "microphone" | "systemAudio"): Promise<unknown>;
    appInfo?(): Promise<{ name?: string; bundleId?: string } | null>;
    onChanged?(cb: () => void): () => void;
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
  /** Meeting drafts on disk. Missing in builds older than local recovery. */
  drafts?: {
    save(draft: object): Promise<{ ok: boolean } | null>;
    list(): Promise<unknown[] | null>;
    remove(id: string): Promise<unknown>;
  };
  /** Only the first-version host (desktop/macos, VocifyHost) has these. */
  capture?: {
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

/** Opens transcript search on the meeting screen (e.g. from the floating pill). */
export const TRANSCRIPT_SEARCH_EVENT = "vocify:transcript-search";
