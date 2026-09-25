import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { ROUTES } from "@/shared/lib/constants";
import { DESKTOP_SHELL_EVENTS, getDesktopBridge, isDesktopHost } from "@/lib/desktop-host";

/** Wires native menu / tray commands to dashboard routes and recorder events. */
export function DesktopShellBridge() {
  const navigate = useNavigate();

  useEffect(() => {
    if (!isDesktopHost()) return;
    const bridge = getDesktopBridge();
    if (!bridge) return;

    return bridge.shell.onCommand((name) => {
      switch (name) {
        case "listen":
          navigate(ROUTES.RECORD);
          queueMicrotask(() => {
            window.dispatchEvent(new CustomEvent(DESKTOP_SHELL_EVENTS.listen));
          });
          break;
        case "stop":
          window.dispatchEvent(new CustomEvent(DESKTOP_SHELL_EVENTS.stop));
          break;
        default:
          break;
      }
    });
  }, [navigate]);

  return null;
}
