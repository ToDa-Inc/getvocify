import { useCallback, useEffect, useState } from "react";
import {
  DESKTOP_PERMISSION,
  desktopPermissionsReady,
  normalizePermissionStatus,
  type DesktopPermissionSnapshot,
  type DesktopPermissionType,
} from "@/lib/desktop-permissions";
import { getDesktopBridge, isDesktopHost } from "@/lib/desktop-host";

const POLL_MS = 1000;

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
  const [openedSettingsRecently, setOpenedSettingsRecently] = useState(false);

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
    return next;
  }, []);

  const request = useCallback(async (type: DesktopPermissionType) => {
    await getDesktopBridge()?.permissions.request(type);
    return refresh();
  }, [refresh]);

  const openSettings = useCallback(
    async (type: DesktopPermissionType) => {
      setOpenedSettingsRecently(true);
      await getDesktopBridge()?.permissions.open(type);
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
    const id = window.setInterval(() => void refresh(), POLL_MS);
    return () => window.clearInterval(id);
  }, [available, refresh]);

  return {
    available,
    loading,
    snapshot,
    ready: desktopPermissionsReady(snapshot),
    appName,
    openedSettingsRecently,
    refresh,
    request,
    openSettings,
  };
}

export { DESKTOP_PERMISSION };
