/**
 * Which microphone the desktop app records the rep with. The system's default is followed until the rep picks one in
 * the island or the app's menu; a picked mic is used whenever it is connected. The last mic that heard the rep is kept
 * too, so a recording that starts on another one (macOS handing the input to the iPhone) can say so.
 * Kept in this page's storage: the dashboard is the one place that can list the mics by name and open them.
 */

export type MicDevice = { id: string; label: string };
/** A picked mic: its id in this page, and its name to find it again if the id changes. */
export type MicChoice = MicDevice;

/** What the island is told: the mics, which one records, and whether to say it is not the usual one. */
export type MicState = {
  devices: MicDevice[];
  /** The system's default input, by name; null when the system names none. */
  defaultLabel: string | null;
  /** The picked mic (connected or not); null: the system's default. */
  chosen: MicChoice | null;
  /** The mic recording now; null when not recording. */
  inUse: string | null;
  /** The recording is not on the rep's usual mic (the picked one is missing, or the default changed). */
  notice: boolean;
};

const CHOICE_KEY = "vocify.desktop.mic";
const USUAL_KEY = "vocify.desktop.mic.usual";

/** Chromium's entries for the system's choices, not mics of their own. */
const SYSTEM_IDS = new Set(["default", "communications"]);
/** "Default - AirPods Pro (Bluetooth)" → "AirPods Pro (Bluetooth)", when no mic shares the default's group. */
const DEFAULT_PREFIX = /^default\s*-\s*/i;

/** The mics the page can see, by name; empty until the page may use the mic (names are hidden before). */
export function micDevices(all: MediaDeviceInfo[]): { devices: MicDevice[]; defaultLabel: string | null } {
  const inputs = all.filter((d) => d.kind === "audioinput" && d.label);
  const mics = inputs.filter((d) => !SYSTEM_IDS.has(d.deviceId));
  const system = inputs.find((d) => d.deviceId === "default");
  // The default entry is the same device as one of the mics (same group): its own name, in any language.
  const same = system ? mics.find((d) => d.groupId && d.groupId === system.groupId) : undefined;
  return {
    devices: mics.map((d) => ({ id: d.deviceId, label: d.label })),
    defaultLabel: same ? same.label : system ? system.label.replace(DEFAULT_PREFIX, "") : null,
  };
}

/**
 * The name of the mic a track opened: the listed mic it is, the system's default by its device's name when it opened
 * "default", else the track's own name without Chromium's "Default - ".
 */
export function micName(label: string, deviceId: string | undefined, list: { devices: MicDevice[]; defaultLabel: string | null }): string | null {
  const listed = list.devices.find((d) => d.id === deviceId)?.label;
  if (listed) return listed;
  if (deviceId === "default" && list.defaultLabel) return list.defaultLabel;
  return label.replace(DEFAULT_PREFIX, "") || null;
}

/** The picked mic among the connected ones: by id, else by name (an id can change when it is plugged in again). */
export function findChosen(devices: MicDevice[], chosen: MicChoice | null): MicDevice | null {
  if (!chosen) return null;
  return devices.find((d) => d.id === chosen.id) ?? devices.find((d) => d.label === chosen.label) ?? null;
}

/** Whether a recording on `inUse` should say so: the picked mic is missing, or nothing was picked and the mic changed. */
export function isUnusual(inUse: string, chosen: MicChoice | null, found: MicDevice | null, usual: string | null): boolean {
  if (chosen) return found === null;
  return usual !== null && usual !== inUse;
}

const read = (key: string): string | null => {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
};
const write = (key: string, value: string | null) => {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* storage unavailable: the choice lasts this session */
  }
};

export function loadChoice(): MicChoice | null {
  try {
    const parsed = JSON.parse(read(CHOICE_KEY) ?? "null") as unknown;
    if (parsed && typeof parsed === "object" && typeof (parsed as MicChoice).id === "string" && typeof (parsed as MicChoice).label === "string") {
      return { id: (parsed as MicChoice).id, label: (parsed as MicChoice).label };
    }
  } catch {
    /* not set or unreadable: the default */
  }
  return null;
}

export function saveChoice(choice: MicChoice | null): void {
  write(CHOICE_KEY, choice ? JSON.stringify(choice) : null);
}

export function loadUsual(): string | null {
  return read(USUAL_KEY);
}

export function saveUsual(label: string): void {
  write(USUAL_KEY, label);
}
