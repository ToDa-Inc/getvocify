/**
 * CRM extraction dates: normalize to ISO YYYY-MM-DD for HubSpot / Salesforce APIs.
 */

import { format, parseISO, isValid } from "date-fns";

/** True for close-date and other date/datetime deal fields in sync preview (not amount/currency). */
export function isCrmDateField(update: { field_name: string; field_type?: string }): boolean {
  const n = (update.field_name || "").toLowerCase();
  const t = (update.field_type || "").toLowerCase();
  // Name wins even if schema type is wrong (e.g. mis-tagged as number)
  if (n.includes("closedate") || n === "closed_date") return true;
  if (t === "number" || t === "currency") return false;
  if (t === "date" || t === "datetime") return true;
  return false;
}

/**
 * Parse common human / locale formats to YYYY-MM-DD.
 * Supports ISO date, DD/MM/YYYY, DD-MM-YYYY, then MM/DD/YYYY if DMY invalid.
 */
export function parseFlexibleDateToIso(input: string | null | undefined): string | null {
  if (input == null) return null;
  const s = String(input).trim();
  if (!s) return null;

  const head = s.slice(0, 10);
  if (/^\d{4}-\d{2}-\d{2}$/.test(head)) {
    const d = parseISO(head);
    return isValid(d) ? head : null;
  }

  const m = s.match(/^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$/);
  if (m) {
    const a = parseInt(m[1], 10);
    const b = parseInt(m[2], 10);
    const y = parseInt(m[3], 10);
    const dmy = new Date(y, b - 1, a);
    if (dmy.getFullYear() === y && dmy.getMonth() === b - 1 && dmy.getDate() === a) {
      return format(dmy, "yyyy-MM-dd");
    }
    const mdy = new Date(y, a - 1, b);
    if (mdy.getFullYear() === y && mdy.getMonth() === a - 1 && mdy.getDate() === b) {
      return format(mdy, "yyyy-MM-dd");
    }
  }

  return null;
}

/** Human-friendly label for display (read-only row). */
export function formatCrmDateForDisplay(raw: string | null | undefined): string {
  const iso = parseFlexibleDateToIso(raw);
  if (!iso) return (raw && String(raw).trim()) || "";
  const d = parseISO(iso);
  return isValid(d) ? format(d, "PPP") : String(raw || "");
}
