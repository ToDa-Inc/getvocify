/**
 * App subdomain URL - used when landing (getvocify.com) and app (app.getvocify.com) are split.
 * Landing links (Get Started, Login) point here. In dev, defaults to current origin.
 */
function resolveAppUrl(): string {
  const env = import.meta.env.VITE_APP_URL;
  if (env) return env.replace(/\/$/, "");
  if (typeof window !== "undefined") {
    const host = window.location.hostname.toLowerCase();
    if (host === "getvocify.com" || host === "www.getvocify.com") return "https://app.getvocify.com";
    return window.location.origin; // app subdomain or localhost
  }
  return "http://localhost:8080";
}
export const APP_URL = resolveAppUrl();

/** Whether we're on the landing domain (marketing site only) */
export function isLandingDomain(): boolean {
  if (typeof window === "undefined") return false;
  const host = window.location.hostname.toLowerCase();
  return host === "getvocify.com" || host === "www.getvocify.com";
}

/** Paths that are valid on the landing domain (no redirect to app) */
const LANDING_PATHS = ["/", "/es"];

export function isLandingPath(path: string): boolean {
  return LANDING_PATHS.includes(path);
}
