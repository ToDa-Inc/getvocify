import { useCallback, useEffect, useRef, useState } from "react";
import {
  DESKTOP_PERMISSION,
  desktopPermissionsBlocker,
  desktopPermissionsReady,
  normalizePermissionStatus,
  type DesktopPermissionSnapshot,
  type DesktopPermissionType,
} from "@/lib/desktop-permissions";
import { getDesktopBridge, isDesktopHost } from "@/lib/desktop-host";

const POLL_MS = 2500;

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
  const [guideActive, setGuideActive] = useState(false);
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
    setLoading(false);
    if (desktopPermissionsReady(next)) setGuideActive(false);
    return next;
  }, []);

  const request = useCallback(
    async (type: DesktopPermissionType) => {
      await getDesktopBridge()?.permissions.request(type);
      return refresh();
    },
    [refresh],
  );

  const guide = useCallback(
    async (type: DesktopPermissionType) => {
      if (snapshotRef.current.signing === "adhoc") return refresh();
      setGuideActive(true);
      await getDesktopBridge()?.permissions.guide(type);
      return refresh();
    },
    [refresh],
  );

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
      const block = desktopPermissionsBlocker(snapshotRef.current);
      if (block !== "none") void refresh();
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
    guideActive,
    refresh,
    request,
    guide,
  };
}

export { DESKTOP_PERMISSION };
