export type EchoCancellation = "all" | "browser" | "off";

/**
 * What the browser really applied to the mic track, which can differ from what was asked: "all" cancels everything the
 * computer plays (Chromium 141+), `true` and "remote-only" the browser's older canceller, which only hears audio played
 * by the page's own connections.
 */
export function appliedEchoCancellation(settings: MediaTrackSettings): EchoCancellation {
  const applied = settings.echoCancellation as boolean | string | undefined;
  if (applied === "all") return "all";
  if (applied === true || applied === "remote-only") return "browser";
  return "off";
}

/** A browser that refuses a value it does not know says so with one of these; a permission or device problem does not. */
function refusedTheValue(error: unknown): boolean {
  return error instanceof Error && (error.name === "TypeError" || error.name === "OverconstrainedError");
}

/** TypeScript's lib types echoCancellation as a boolean; "all" (Chromium 141+) is a string. */
type AudioConstraints = {
  echoCancellation: boolean | { ideal: string };
  noiseSuppression: boolean;
  autoGainControl: boolean;
  deviceId?: { exact: string };
};

function ask(getUserMedia: (constraints: MediaStreamConstraints) => Promise<MediaStream>, audio: AudioConstraints) {
  return getUserMedia({ audio: audio as MediaTrackConstraints });
}

/**
 * The rep's mic, asking for the canceller that hears everything the computer plays. Chromium before 141 reads
 * `{ ideal: "all" }` as `true`, so those builds get what they always had; a browser that throws gets asked once more
 * the old way. `deviceId` opens that mic instead of the system's default.
 */
export async function openRepMic(
  getUserMedia: (constraints: MediaStreamConstraints) => Promise<MediaStream>,
  deviceId?: string,
): Promise<{ stream: MediaStream; echoCancellation: EchoCancellation }> {
  const device = deviceId ? { deviceId: { exact: deviceId } } : {};
  let stream: MediaStream;
  try {
    stream = await ask(getUserMedia, { echoCancellation: { ideal: "all" }, noiseSuppression: true, autoGainControl: true, ...device });
  } catch (error) {
    if (!refusedTheValue(error) || (deviceId && error instanceof Error && error.name === "OverconstrainedError")) throw error;
    stream = await ask(getUserMedia, { echoCancellation: true, noiseSuppression: true, autoGainControl: true, ...device });
  }
  return { stream, echoCancellation: appliedEchoCancellation(stream.getAudioTracks()[0].getSettings()) };
}

/**
 * Whether the server's canceller works on the rep's side, and which mic it is told about. A page mic that cancels
 * everything the computer plays (applied "all") has nothing left for it to take out; the native mic and the other
 * page mics still do. Not a meeting (echoCancel off, e.g. a Vocify call): never.
 */
export function serverEchoCancel(
  echoCancel: boolean,
  nativeMic: boolean,
  pageMicApplied: EchoCancellation | null,
): "native" | "page" | undefined {
  const pageMicIsClean = !nativeMic && pageMicApplied === "all";
  if (!echoCancel || pageMicIsClean) return undefined;
  return nativeMic ? "native" : "page";
}
