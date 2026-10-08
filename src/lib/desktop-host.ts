/** The Vocify Mac app's WKWebView bridge, injected by the native shell's bridge.js. */
export type DesktopPermissionStatus = "authorized" | "denied" | "never_requested";

/** `label` is null when the shortcut is off. */
export type RecordShortcutState = { label: string | null; defaultLabel: string };

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
      /** Reading the CRM tab in the rep's browsers (Mac Automation). Missing in builds without calling. */
      crmTabs?: DesktopPermissionStatus | "unavailable";
      signing?: "adhoc" | "signed";
      signingAuthority?: string;
      systemAudioError?: string;
    }>;
    request(type: "microphone" | "systemAudio" | "crmTabs"): Promise<unknown>;
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
    /** Quits and reopens this copy of the app. Missing in older builds. */
    relaunch?(): Promise<unknown>;
    command(name: string): void;
    onCommand(cb: (name: string) => void): () => void;
    /** Live help events for the Mac's log (written only while its test switch is on). */
    log?(name: string, details?: Record<string, unknown>): void;
    onOverlayState?(cb: (state: Record<string, unknown>) => void): () => void;
    /** The call type picked in the island while recording ({ key: null }: Vocify decides). */
    onCallType?(cb: (payload: { key: string | null }) => void): () => void;
    /** The channel the rep switched to in the island (types by channel): sent when `liveType.channel`
     * is shown and not `fixed`. An island that does not know the field never sends it. */
    onCallChannel?(cb: (payload: { kind: "call" | "meeting" }) => void): () => void;
    /** A choice made in the island's post-call card: { type, ...details }. */
    onPostCallAction?(cb: (action: { type: string; [key: string]: unknown }) => void): () => void;
  };
  saas: {
    request(payload: Record<string, unknown>): Promise<{
      ok: boolean;
      status?: number;
      data?: unknown;
      error?: string;
    }>;
  };
  /** CRM pages open in the rep's browsers. Missing in builds older than the call contact. */
  crm?: {
    pages(options?: { ask?: boolean }): Promise<{
      urls: string[];
      browsers: { name: string; bundleId: string; access: string }[];
    }>;
    openAutomationSettings(): Promise<unknown>;
    /** The notch island detected a call with these CRM pages on screen. */
    onCallPages(cb: (payload: { urls: string[] }) => void): () => void;
    /** The detected call ended (the call app let go of the mic). */
    onCallEnded?(cb: () => void): () => void;
    /**
     * The CRM pages in the frontmost browser changed (the island's phone offer follows them).
     * `[]`: no CRM record any more. Missing in builds without calling.
     */
    onScreen?(cb: (payload: { urls: string[] }) => void): () => void;
    /** Where the detected call happens; null when it can't be told. */
    onCallSource?(cb: (source: { name: string; kind: "call" | "meeting" | null } | null) => void): () => void;
  };
  /**
   * Who the meeting app shows speaking while a call is recorded in the page (Mac: Zoom, and Google Meet
   * through the Vocify extension). Missing on Windows and in older builds.
   */
  speakers?: {
    onSpeaking?(cb: (payload: { names: string[] }) => void): () => void;
  };
  /** The global record shortcut. Missing in older builds. */
  shortcut?: {
    get(): Promise<RecordShortcutState>;
    set(combo: { code: string; meta: boolean; alt: boolean; ctrl: boolean; shift: boolean }): Promise<
      RecordShortcutState & { ok: boolean; reason?: "invalid" | "taken" }
    >;
    clear(): Promise<RecordShortcutState>;
  };
  /**
   * The Mac records the call itself: mic, call audio and transcription socket. The page gets
   * copies of the transcript (a MeetingTranscript) and levels. Missing in older builds.
   */
  recorder?: {
    /** `ticket` is sent first on every connection (the live service requires it). */
    start(options: { url: string; ticket?: string }): Promise<{ ok: boolean; reason?: string }>;
    pause(paused: boolean): Promise<unknown>;
    stop(): Promise<{ transcript: unknown } | null>;
    onTranscript(cb: (transcript: unknown) => void): () => void;
    onLevels(cb: (levels: { you: number; them: number }) => void): () => void;
    onWarning(cb: (payload: { text: string | null }) => void): () => void;
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

/** A memo changed outside its page (e.g. approved from the island): its page reloads it. */
export const MEMO_CHANGED_EVENT = "vocify:memo-changed";

/** Opens transcript search on the meeting screen (e.g. from the floating pill). */
export const TRANSCRIPT_SEARCH_EVENT = "vocify:transcript-search";
