import { useCallback, useEffect, useRef, useState } from "react";
import { desktopPlatform, getDesktopBridge } from "@/lib/desktop-host";
import { hookMicPcm, LIVE_STT_SAMPLE_RATE } from "@/lib/copilot-channel-stt";
import { peak, pcmLevel, SILENT_PEAK } from "@/lib/audio-health";

/** Long enough to say something and play a few seconds of a video; it stops by itself after. */
const CHECK_MS = 20_000;

type Side = "you" | "them";

/**
 * A short test of both inputs outside a meeting: the mic, and the call audio the desktop app captures. `heard` turns
 * true once a side sends real sound, so a side that stays flat is visible before the next call, not during it.
 */
export function useAudioCheck() {
  const [running, setRunning] = useState(false);
  const [levels, setLevels] = useState({ you: 0, them: 0 });
  const [heard, setHeard] = useState({ you: false, them: false });
  const [problem, setProblem] = useState<{ side: Side; text: string } | null>(null);
  const releaseRef = useRef<(() => void)[]>([]);
  const levelRef = useRef({ you: 0, them: 0 });
  /** Bumped by every start and stop: a start still opening devices when stopped lets go of them. */
  const runRef = useRef(0);

  const stop = useCallback(() => {
    runRef.current += 1;
    releaseRef.current.forEach((release) => release());
    releaseRef.current = [];
    levelRef.current = { you: 0, them: 0 };
    setLevels({ you: 0, them: 0 });
    setRunning(false);
  }, []);

  const start = useCallback(async () => {
    const bridge = getDesktopBridge();
    if (!bridge) return;
    stop();
    const run = runRef.current;
    /** Keeps a release while this run is current, else runs it now. */
    const keep = (release: () => void) => {
      if (runRef.current === run) releaseRef.current.push(release);
      else release();
    };
    setProblem(null);
    setHeard({ you: false, them: false });
    setRunning(true);

    const hear = (side: Side) => (pcm: ArrayBuffer) => {
      levelRef.current[side] = Math.max(levelRef.current[side] * 0.85, pcmLevel(pcm));
      if (peak(new Int16Array(pcm)) > SILENT_PEAK) setHeard((prev) => (prev[side] ? prev : { ...prev, [side]: true }));
    };

    try {
      const mic = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
      const ctx = new AudioContext({ sampleRate: LIVE_STT_SAMPLE_RATE });
      if (ctx.state === "suspended") await ctx.resume();
      const unhook = hookMicPcm(ctx, mic, hear("you"));
      keep(() => {
        unhook();
        mic.getTracks().forEach((track) => track.stop());
        void ctx.close();
      });
    } catch {
      setProblem({ side: "you", text: "Vocify couldn't open the microphone. Allow it above." });
    }

    const started = await bridge.systemAudio.start().catch(() => ({ ok: false, reason: undefined }));
    if (started.ok) {
      const off = bridge.systemAudio.onPcm(hear("them"));
      keep(() => {
        off();
        void bridge.systemAudio.stop();
      });
    } else {
      setProblem((prev) =>
        prev ?? {
          side: "them",
          text:
            started.reason === "needs_restart"
              ? "Call audio is on but Vocify needs a restart to use it."
              : desktopPlatform() === "darwin"
                ? "Vocify couldn't capture call audio. Allow it above."
                : "Vocify couldn't capture call audio. Check a speaker or headset is connected.",
        },
      );
    }

    if (runRef.current !== run) return;
    const tick = window.setInterval(() => {
      const { you, them } = levelRef.current;
      setLevels({ you, them });
      levelRef.current = { you: you * 0.6, them: them * 0.6 };
    }, 125);
    const end = window.setTimeout(stop, CHECK_MS);
    keep(() => {
      window.clearInterval(tick);
      window.clearTimeout(end);
    });
  }, [stop]);

  useEffect(() => stop, [stop]);

  return { running, levels, heard, problem, start, stop };
}
