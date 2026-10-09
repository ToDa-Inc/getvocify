import { useLayoutEffect, type ReactNode } from "react";
import { resolveTheme } from "@/lib/theme-mode";
import { setAppliedTheme, useThemeMode } from "@/lib/theme-store";

/*
  Dark mode is the dashboard's alone: the `dark` class goes on <html> (so portals — menus, sheets,
  dialogs, toasts — pick it up) only while DashboardThemeProvider is mounted. Login and the
  marketing pages never mount it, so they stay light whatever the choice.
*/

const DARK_QUERY = "(prefers-color-scheme: dark)";

function darkQuery(): MediaQueryList | null {
  try {
    return window.matchMedia(DARK_QUERY);
  } catch {
    return null;
  }
}

/** Paints its children's routes (and their portals) in the chosen theme while mounted. */
export function DashboardThemeProvider({ children }: { children: ReactNode }) {
  const { mode } = useThemeMode();

  useLayoutEffect(() => {
    const root = document.documentElement;
    const media = darkQuery();
    const apply = () => {
      const next = resolveTheme(mode, media?.matches ?? false);
      root.classList.toggle("dark", next === "dark");
      root.style.colorScheme = next === "dark" ? "dark" : "";
      setAppliedTheme(next);
    };
    apply();
    if (mode !== "system" || !media) return;
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [mode]);

  useLayoutEffect(
    () => () => {
      const root = document.documentElement;
      root.classList.remove("dark");
      root.style.colorScheme = "";
      setAppliedTheme("light");
    },
    [],
  );

  return <>{children}</>;
}
