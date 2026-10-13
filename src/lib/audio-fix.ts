/**
 * What Vocify learned about audio that is allowed but doesn't work, kept per computer so the permission rows can say
 * so after a relaunch. macOS can list Vocify as allowed in Screen & System Audio Recording and still refuse the
 * capture (most often after the app was rebuilt or re-signed: the switch belongs to the old copy). Its check then
 * reads "authorized", so only a failed capture shows it.
 */

/** `toggle`: switch Vocify off and on. `readd`: that wasn't enough, remove it with − and add it with +. */
export type CallAudioFix = { step: "toggle" | "readd"; relaunched: boolean };

export type AudioFixEvent = "failed" | "relaunching" | "worked";

/** Capture refusals that are not this case: the switch is off (the normal row handles it) or a capture is running. */
const NOT_A_BROKEN_GRANT = new Set(["permission_denied", "needs_restart", "already_running", "unsupported_platform"]);

export function isBrokenGrant(reason: string | undefined): boolean {
  return !NOT_A_BROKEN_GRANT.has(reason ?? "");
}

/** Failing again after relaunching for a fix moves on to the stronger fix. */
export function nextCallAudioFix(current: CallAudioFix | null, event: AudioFixEvent): CallAudioFix | null {
  if (event === "worked") return null;
  if (event === "relaunching") return current ? { ...current, relaunched: true } : null;
  if (!current) return { step: "toggle", relaunched: false };
  if (current.relaunched) return { step: "readd", relaunched: false };
  return current;
}

const CALL_KEY = "vocify.desktop.callAudioFix";
const MIC_KEY = "vocify.desktop.micSilent";
const CHANGED = "vocify:audio-fix-changed";

function read<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function write(key: string, value: unknown): void {
  try {
    if (value === null || value === false) localStorage.removeItem(key);
    else localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage blocked: the rows fall back to what the system reports.
  }
  window.dispatchEvent(new Event(CHANGED));
}

export function readCallAudioFix(): CallAudioFix | null {
  const value = read<CallAudioFix>(CALL_KEY);
  return value && (value.step === "toggle" || value.step === "readd") ? { step: value.step, relaunched: value.relaunched === true } : null;
}

export function reportCallAudio(event: AudioFixEvent): void {
  const current = readCallAudioFix();
  const next = nextCallAudioFix(current, event);
  if (JSON.stringify(next) !== JSON.stringify(current)) write(CALL_KEY, next);
}

/** The mic is allowed but a recording got only silence from it; cleared once it sends sound again. */
export function readMicSilent(): boolean {
  return read<boolean>(MIC_KEY) === true;
}

export function reportMicSilent(silent: boolean): void {
  if (readMicSilent() !== silent) write(MIC_KEY, silent);
}

export function onAudioFixChanged(cb: () => void): () => void {
  const onStorage = (event: StorageEvent) => {
    if (event.key === CALL_KEY || event.key === MIC_KEY) cb();
  };
  window.addEventListener(CHANGED, cb);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(CHANGED, cb);
    window.removeEventListener("storage", onStorage);
  };
}
