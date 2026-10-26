/** The Vocify desktop app's WKWebView (Mac) or Electron (Windows) bridge, injected by the native shell's bridge.js. */
export type DesktopPermissionStatus = "authorized" | "denied" | "never_requested";

/** `label` is null when the shortcut is off. */
export type RecordShortcutState = { label: string | null; defaultLabel: string };

/** Vocify calling on this computer: `onPhone`, the island's Call opens in `phoneApp` (null: this computer has none). */
export type DesktopCalling = { onPhone: boolean; phoneApp: string | null };

/** The island's own settings on this computer (the tray's "Hide island" is the same switch). */
export type IslandAppearance = "auto" | "light" | "dark";
/** Where the island sits: the notch at the top, or a strip at the side of the screen. */
export type IslandPlacement = "notch" | "side";
/** What the island's settings report; each app reports only the settings it has. */
export type IslandState = { appearance?: IslandAppearance; visible?: boolean; placement?: IslandPlacement };

export type VocifyDesktopBridge = {
  platform: "darwin" | "win32";
  systemAudio: {
    /**
     * `mic`: the app also captures the rep's microphone with the call where it can, answered `mic: true` (then
     * `nativeMic` carries it). Builds without it ignore the option and answer without `mic`.
     */
    start(options?: { mic?: boolean }): Promise<{ ok: boolean; backend?: string; reason?: string; mic?: boolean }>;
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
    /**
     * What the rep did in the island's live call assistant (flag LIVE_BRAIN_ENABLED): responder, preguntar, resumen, tick,
     * untick, dismiss; with the "Qué decir" view also rewrite, ask_step, responder_turn and event (build contract 2026-10-20, §5).
     */
    onLiveAction?(cb: (action: { type: string; [key: string]: unknown }) => void): () => void;
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
  /**
   * The microphone the app captured with the call (`systemAudio.start({ mic: true })` answered `mic: true`), raw, in
   * 100 ms PCM frames, each just before the call's frame of the same moment. Missing in older builds.
   */
  nativeMic?: {
    onPcm(cb: (pcm: ArrayBuffer) => void): () => void;
  };
  /**
   * Only in the desktop app run from source: keeps a recording's raw audio per side on the computer, to replay real
   * calls offline. Missing everywhere else.
   */
  devTrace?: {
    audio(side: string, pcm: ArrayBuffer, at: number, recording: number): void;
  };
  /**
   * The dashboard's own window: compact is a small window at the side of the screen, above the call, for the live view
   * only. Missing in older builds (and in the Mac app).
   */
  window?: {
    get(): Promise<{ compact: boolean }>;
    setCompact(compact: boolean): Promise<{ compact: boolean }>;
    onCompact(cb: (payload: { compact: boolean }) => void): () => void;
  };
  /** Vocify calling on this computer; off, the island's Call opens on the rep's own phone. Missing in older builds. */
  calling?: {
    get(): Promise<DesktopCalling>;
    set(onPhone: boolean): Promise<DesktopCalling>;
    /** Opens the call there; the island records it once it connects. */
    dialOnPhone(number: string): Promise<{ ok: boolean; reason?: string }>;
    /** Opens where calls from the phone are set up (Mac: FaceTime; Windows: Default apps). Missing in older builds. */
    setup?(): Promise<unknown>;
    /** Opens where the call's microphone is chosen (Mac: FaceTime; Windows: Sound › Recording). Missing in older builds. */
    micSettings?(): Promise<unknown>;
  };
  /** The island's settings on this computer (appearance, whether it shows, where it sits). Missing in older builds. */
  island?: {
    get(): Promise<IslandState>;
    /** Each setter exists only where the app offers that setting (the Electron app: placement only, so far). */
    setAppearance?(appearance: IslandAppearance): Promise<IslandState>;
    setVisible?(visible: boolean): Promise<IslandState>;
    setPlacement?(placement: IslandPlacement): Promise<IslandState>;
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
  return (
    typeof window !== "undefined" &&
    (window.vocifyDesktop?.platform === "darwin" || window.vocifyDesktop?.platform === "win32")
  );
}

export function desktopPlatform(): "darwin" | "win32" | null {
  if (typeof window === "undefined") return null;
  const platform = window.vocifyDesktop?.platform;
  if (platform === "darwin" || platform === "win32") return platform;
  return null;
}

export function getDesktopBridge(): VocifyDesktopBridge | null {
  return isDesktopHost() ? window.vocifyDesktop! : null;
}

/** A memo changed outside its page (e.g. approved from the island): its page reloads it. */
export const MEMO_CHANGED_EVENT = "vocify:memo-changed";

/** Opens transcript search on the meeting screen (e.g. from the floating pill). */
export const TRANSCRIPT_SEARCH_EVENT = "vocify:transcript-search";

/**
 * Click handler for a link that leaves Vocify. The desktop app's web view ignores `target="_blank"`
 * (nothing opens), so there the page is handed to the Mac or Windows default browser; in a browser the
 * link works as it is.
 */
export function openExternalLink(event: { preventDefault: () => void }, url: string): void {
  const bridge = getDesktopBridge();
  if (!bridge) return;
  event.preventDefault();
  void bridge.shell.openExternal(url);
}
