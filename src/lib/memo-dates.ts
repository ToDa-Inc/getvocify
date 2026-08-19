import { format, formatDistanceToNow, isValid } from "date-fns";

export function parseRecordedAt(value: string | number | null | undefined): Date | null {
  if (value == null || value === "") return null;
  if (typeof value === "number" && Number.isFinite(value)) {
    const ms = value < 1e12 ? value * 1000 : value;
    const d = new Date(ms);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  const d = new Date(String(value));
  return Number.isNaN(d.getTime()) ? null : d;
}

/** e.g. "Aug 19, 2026 · 3:35 PM" */
export function formatRecordedAt(value: string | number | null | undefined): string {
  const d = parseRecordedAt(value);
  if (!d || !isValid(d)) return "";
  return format(d, "MMM d, yyyy · h:mm a");
}

/** Date + relative time for list rows. */
export function formatRecordedAtLabel(value: string | number | null | undefined): string {
  const d = parseRecordedAt(value);
  if (!d || !isValid(d)) return "";
  return `${format(d, "MMM d, yyyy · h:mm a")} (${formatDistanceToNow(d, { addSuffix: true })})`;
}
