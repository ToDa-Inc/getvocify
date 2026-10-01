/** The tab a `?tab=` value selects: the value itself when this page offers it, else the fallback. */
export function parseTab<T extends string>(raw: string | null, allowed: readonly T[], fallback: T): T {
  return allowed.includes(raw as T) ? (raw as T) : fallback;
}
