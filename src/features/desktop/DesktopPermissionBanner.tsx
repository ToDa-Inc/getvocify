import { AlertCircle } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { ROUTES } from "@/shared/lib/constants";
import { desktopPlatform } from "@/lib/desktop-host";
import { useDesktopPermissions } from "./useDesktopPermissions";

const SYSTEM_SETTINGS = "/dashboard/settings/system";

/**
 * On every page of the desktop app while mic or call audio is off: a recording without them is silence, and nothing
 * else says so until the memo comes back empty. The Record page and System settings show the full rows instead.
 */
export function DesktopPermissionBanner() {
  const { available, loading, snapshot, blocker } = useDesktopPermissions();
  const { pathname } = useLocation();
  if (!available || loading || blocker === "none") return null;
  if (pathname === ROUTES.RECORD || pathname === SYSTEM_SETTINGS) return null;

  const micOff = snapshot.microphone !== "authorized";
  const callOff = desktopPlatform() !== "win32" && snapshot.systemAudio !== "authorized";
  const what = micOff && callOff ? "your mic and call audio" : micOff ? "your mic" : "call audio";

  return (
    <div className="flex items-center gap-2 border-b border-border/60 bg-warning/10 px-6 py-2 text-xs md:px-8" role="status">
      <AlertCircle className="h-3.5 w-3.5 shrink-0 text-warning" />
      <p className="min-w-0 flex-1 text-foreground">Vocify can't use {what}, so recordings will miss it.</p>
      <Link to={SYSTEM_SETTINGS} className="shrink-0 font-medium text-foreground underline-offset-2 hover:underline">
        Fix in Settings
      </Link>
    </div>
  );
}
