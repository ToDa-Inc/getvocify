import { useCallback, useEffect, useState } from "react";
import {
  isBrokenGrant,
  onAudioFixChanged,
  readCallAudioFix,
  readMicSilent,
  reportCallAudio,
  type CallAudioFix,
} from "@/lib/audio-fix";
import { getDesktopBridge } from "@/lib/desktop-host";

/** Audio that is allowed but didn't work, as this computer last saw it, and a quick test of the call audio. */
export function useAudioFix() {
  const [callFix, setCallFix] = useState<CallAudioFix | null>(readCallAudioFix);
  const [micSilent, setMicSilent] = useState(readMicSilent);
  const [testing, setTesting] = useState(false);

  useEffect(
    () =>
      onAudioFixChanged(() => {
        setCallFix(readCallAudioFix());
        setMicSilent(readMicSilent());
      }),
    [],
  );

  /** Starts the call audio capture and stops it at once: the only way to know macOS hands it over. */
  const testCallAudio = useCallback(async () => {
    const bridge = getDesktopBridge();
    if (!bridge) return;
    setTesting(true);
    try {
      const started = await bridge.systemAudio.start();
      if (started.ok) {
        await bridge.systemAudio.stop();
        reportCallAudio("worked");
      } else if (isBrokenGrant(started.reason)) {
        reportCallAudio("failed");
      }
    } finally {
      setTesting(false);
    }
  }, []);

  return { callFix, micSilent, testing, testCallAudio };
}
