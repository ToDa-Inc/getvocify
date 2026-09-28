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
    showOverlay(): Promise<unknown>;
    hideOverlay(): Promise<unknown>;
    openExternal(url: string): Promise<{ ok?: boolean }>;
    command(name: string): void;
    onCommand(cb: (name: string) => void): () => void;
  };
  /** Meeting drafts on disk. Missing in builds older than local recovery. */
  drafts?: {
    save(draft: object): Promise<{ ok: boolean } | null>;
    list(): Promise<unknown[] | null>;
    remove(id: string): Promise<unknown>;
  };
};

declare global {
  interface Window {
    vocifyDesktop?: VocifyDesktopBridge;
  }
}

export function isDesktopHost(): boolean {
  return typeof window !== "undefined" && window.vocifyDesktop?.platform === "darwin";
}

export function getDesktopBridge(): VocifyDesktopBridge | null {
  return isDesktopHost() ? window.vocifyDesktop! : null;
}
