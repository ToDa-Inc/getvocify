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

/** Booking link for the demo call (founder-led sales, no self-serve signup yet) */
export const DEMO_BOOKING_URL =
  "https://meetings-eu1.hubspot.com/dani-zal?uuid=e04c2511-8c6b-424b-8dd9-b5eddfe1e87c";

/** Whether we're on the landing domain (marketing site only) */
export function isLandingDomain(): boolean {
  if (typeof window === "undefined") return false;
  const host = window.location.hostname.toLowerCase();
  return host === "getvocify.com" || host === "www.getvocify.com";
}

/** Paths that are valid on the landing domain (no redirect to app) */
const LANDING_PATHS = ["/", "/en", "/privacy", "/about", "/blog", "/terms"];

export function isLandingPath(path: string): boolean {
  return LANDING_PATHS.includes(path);
}
