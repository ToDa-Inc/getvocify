import { useCallback, useEffect, useRef, useState } from "react";
import {
  DESKTOP_PERMISSION,
  desktopPermissionsBlocker,
  desktopPermissionsReady,
  normalizePermissionStatus,
  permissionAction,
  systemAudioHint,
  type DesktopPermissionSnapshot,
  type DesktopPermissionType,
} from "@/lib/desktop-permissions";
import { getDesktopBridge, isDesktopHost } from "@/lib/desktop-host";

const POLL_MS = 2500;
/** Set just before relaunching for system audio, so the reopened app knows a restart didn't fix it. */
const RELAUNCHED_KEY = "vocify.desktop.relaunchedForSystemAudio";

function readRelaunched(): boolean {
  try {
    return localStorage.getItem(RELAUNCHED_KEY) === "1";
  } catch {
    return false;
  }
}

function writeRelaunched(on: boolean) {
  try {
    if (on) localStorage.setItem(RELAUNCHED_KEY, "1");
    else localStorage.removeItem(RELAUNCHED_KEY);
  } catch {
    // Storage blocked: the hint falls back to "relaunch".
  }
}

const EMPTY: DesktopPermissionSnapshot = {
  platform: "darwin",
  microphone: "never_requested",
  systemAudio: "never_requested",
};

function parseSnapshot(raw: Record<string, unknown>): DesktopPermissionSnapshot {
  return {
    platform: String(raw.platform ?? "darwin"),
    microphone: normalizePermissionStatus(raw.microphone),
    systemAudio: normalizePermissionStatus(raw.systemAudio),
    signing: raw.signing === "signed" ? "signed" : raw.signing === "adhoc" ? "adhoc" : undefined,
    signingAuthority: typeof raw.signingAuthority === "string" ? raw.signingAuthority : undefined,
    systemAudioError: typeof raw.systemAudioError === "string" ? raw.systemAudioError : undefined,
  };
}

export function useDesktopPermissions() {
  const available = isDesktopHost();
  const [snapshot, setSnapshot] = useState<DesktopPermissionSnapshot>(EMPTY);
  const [appName, setAppName] = useState("Vocify");
  const [loading, setLoading] = useState(available);
  const [systemAudioAsked, setSystemAudioAsked] = useState(false);
  const [relaunched, setRelaunched] = useState(readRelaunched);
  const snapshotRef = useRef(snapshot);
  snapshotRef.current = snapshot;

  const refresh = useCallback(async () => {
    const bridge = getDesktopBridge();
    if (!bridge) {
      setLoading(false);
      return EMPTY;
    }
    const raw = (await bridge.permissions.status()) as Record<string, unknown>;
    const next = parseSnapshot(raw);
    setSnapshot(next);
    if (next.systemAudio === "authorized") {
      writeRelaunched(false);
      setRelaunched(false);
    }
    setLoading(false);
    return next;
  }, []);

  const request = useCallback(
    async (type: DesktopPermissionType) => {
      const bridge = getDesktopBridge();
      if (!bridge) return refresh();

      const status = type === DESKTOP_PERMISSION.microphone ? snapshotRef.current.microphone : snapshotRef.current.systemAudio;
      const action = permissionAction(status);
      if (type === DESKTOP_PERMISSION.systemAudio) setSystemAudioAsked(true);

      if (action === "open_settings") {
        await bridge.permissions.open(type);
      } else {
        await bridge.permissions.request(type);
      }
      return refresh();
    },
    [refresh],
  );

  const relaunch = useCallback(async () => {
    const bridge = getDesktopBridge();
    if (!bridge?.shell.relaunch) return;
    writeRelaunched(true);
    await bridge.shell.relaunch();
  }, []);

  useEffect(() => {
    if (!available) return;
    void refresh();
    void getDesktopBridge()
      ?.permissions.appInfo?.()
      .then((info) => {
        if (info && typeof info === "object" && "name" in info && typeof info.name === "string") {
          setAppName(info.name);
        }
      })
      .catch(() => {});

    const bridge = getDesktopBridge();
    const offChanged = bridge?.permissions.onChanged?.(() => void refresh());

    const id = window.setInterval(() => {
      if (desktopPermissionsBlocker(snapshotRef.current) !== "none") void refresh();
    }, POLL_MS);

    return () => {
      window.clearInterval(id);
      offChanged?.();
    };
  }, [available, refresh]);

  return {
    available,
    loading,
    snapshot,
    blocker: desktopPermissionsBlocker(snapshot),
    ready: desktopPermissionsReady(snapshot),
    appName,
    refresh,
    request,
    systemAudioHint: systemAudioHint(snapshot.systemAudio, { asked: systemAudioAsked, relaunched }),
    /** Older Mac builds can't relaunch themselves; they keep the "quit and reopen" copy. */
    canRelaunch: Boolean(available && getDesktopBridge()?.shell.relaunch),
    relaunch,
  };
}

export { DESKTOP_PERMISSION };
