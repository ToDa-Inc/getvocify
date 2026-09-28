/**
 * Lista 4 (E8): the Head of Sales' follow-up cadence editor (Ajustes → Oferta). Same rules as
 * the backend (hoy/cadence.py + PATCH /company): known stoppers, whole days from 1 to 90.
 */

export const CADENCE_STOPPERS = [
  "interest_high",
  "interest_medium",
  "interest_low",
  "price",
  "authority",
  "trust",
  "competitor",
  "status_quo",
  "timing",
  "other",
] as const;

export type CadenceStopper = (typeof CADENCE_STOPPERS)[number];
export const CADENCE_MIN_DAYS = 1;
export const CADENCE_MAX_DAYS = 90;

/** What the inputs show: the override where there is one, else the default. */
export function cadenceInputs(
  overrides: Record<string, number> | null | undefined,
  defaults: Record<string, number> | null | undefined,
): Record<CadenceStopper, string> {
  const out = {} as Record<CadenceStopper, string>;
  for (const stopper of CADENCE_STOPPERS) {
    const value = overrides?.[stopper] ?? defaults?.[stopper];
    out[stopper] = value == null ? "" : String(value);
  }
  return out;
}

export function validDays(value: string): boolean {
  const days = Number(value);
  return /^\d+$/.test(value.trim()) && Number.isInteger(days) && days >= CADENCE_MIN_DAYS && days <= CADENCE_MAX_DAYS;
}

/** The overrides to save: only the waits that differ from the default, so a later change of a
 * default still reaches the company. null while any input is not a valid number of days. */
export function cadenceOverrides(
  inputs: Record<CadenceStopper, string>,
  defaults: Record<string, number> | null | undefined,
): Record<string, number> | null {
  const out: Record<string, number> = {};
  for (const stopper of CADENCE_STOPPERS) {
    const value = inputs[stopper] ?? "";
    if (!validDays(value)) return null;
    const days = Number(value);
    if (days !== defaults?.[stopper]) out[stopper] = days;
  }
  return out;
}
