import { useSyncExternalStore } from "react";
import { THEME_STORAGE_KEY, parseThemeMode, type ResolvedTheme, type ThemeMode } from "./theme-mode.ts";

/*
  The theme choice and what is painted, shared by the avatar menu, the dashboard's
  DashboardThemeProvider and the toaster (which lives outside the dashboard).
*/

let storedMode: ThemeMode | null = null;
let appliedTheme: ResolvedTheme = "light";
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** The stored choice ("system" when storage is empty, garbage or unavailable). Read once. */
export function getThemeMode(): ThemeMode {
  if (storedMode === null) {
    try {
      storedMode = parseThemeMode(window.localStorage.getItem(THEME_STORAGE_KEY));
    } catch {
      storedMode = "system";
    }
  }
  return storedMode;
}

/** Changes the choice; if storage is unavailable it still holds for this session. */
export function setThemeMode(next: ThemeMode) {
  storedMode = next;
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, next);
  } catch {
    // Storage unavailable: the choice holds for this session only.
  }
  emit();
}

/** The avatar menu's Tema: the stored choice and a setter. */
export function useThemeMode(): { mode: ThemeMode; setMode: (mode: ThemeMode) => void } {
  const mode = useSyncExternalStore(subscribe, getThemeMode, () => "system" as const);
  return { mode, setMode: setThemeMode };
}

/** The theme painted right now: the dashboard's resolved choice, "light" everywhere else. */
export function useAppliedTheme(): ResolvedTheme {
  return useSyncExternalStore(subscribe, () => appliedTheme, () => "light" as const);
}

/** Records what the dashboard painted, so the toaster can follow it. */
export function setAppliedTheme(next: ResolvedTheme) {
  if (appliedTheme === next) return;
  appliedTheme = next;
  emit();
}
