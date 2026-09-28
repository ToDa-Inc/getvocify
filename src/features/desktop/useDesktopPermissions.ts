import { useCallback, useEffect, useRef, useState } from "react";
import {
  DESKTOP_PERMISSION,
  desktopPermissionsReady,
  normalizePermissionStatus,
  type DesktopPermissionSnapshot,
  type DesktopPermissionType,
} from "@/lib/desktop-permissions";
import { getDesktopBridge, isDesktopHost } from "@/lib/desktop-host";

const POLL_MS = 2000;

const EMPTY: DesktopPermissionSnapshot = {
  platform: "darwin",
  microphone: "never_requested",
  systemAudio: "never_requested",
};

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
    const raw = await bridge.permissions.status();
    const next: DesktopPermissionSnapshot = {
      platform: raw.platform,
      microphone: normalizePermissionStatus(raw.microphone),
      systemAudio: normalizePermissionStatus(raw.systemAudio),
    };
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

  /** Opens the native floating drag card beside System Settings (Codex flow). */
  const guide = useCallback(
    async (type: DesktopPermissionType) => {
      setGuideActive(true);
      await getDesktopBridge()?.permissions.guide(type);
      return refresh();
    },
    [refresh],
  );

  const openSettings = useCallback(
    async (type: DesktopPermissionType) => {
      await guide(type);
    },
    [guide],
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
      if (!desktopPermissionsReady(snapshotRef.current)) void refresh();
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
    ready: desktopPermissionsReady(snapshot),
    appName,
    guideActive,
    refresh,
    request,
    guide,
    openSettings,
  };
}

export { DESKTOP_PERMISSION };
