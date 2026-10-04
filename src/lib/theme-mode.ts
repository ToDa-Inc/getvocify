/** The dashboard's theme choice: Claro, Oscuro or Sistema (follow the OS). */
export type ThemeMode = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "vocify-theme";

/** A stored value becomes a mode; anything unknown means "follow the system". */
export function parseThemeMode(raw: unknown): ThemeMode {
  return raw === "light" || raw === "dark" || raw === "system" ? raw : "system";
}

/** The theme actually painted: an explicit choice wins, "system" follows the OS. */
export function resolveTheme(mode: ThemeMode, prefersDark: boolean): ResolvedTheme {
  if (mode === "system") return prefersDark ? "dark" : "light";
  return mode;
}
