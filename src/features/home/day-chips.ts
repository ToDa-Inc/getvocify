import type { TodayFocus } from "@/lib/home-rail";
import type { ProductTranslations } from "@/lib/product-catalog";

export const TODAY_PATH = "/dashboard/today";

/** Hoy opened on one part of the day (Inicio's chips); without a focus, the whole day. */
export function todayHref(focus: TodayFocus | null): string {
  return focus ? `${TODAY_PATH}?focus=${focus}` : TODAY_PATH;
}

export function focusLabel(focus: TodayFocus, copy: ProductTranslations): string {
  switch (focus) {
    case "meetings":
      return copy.home_meetings;
    case "needs_ok":
      return copy.home_needs_ok;
    case "tasks":
      return copy.home_tasks;
    case "followups":
      return copy.home_followups;
    case "new":
      return copy.home_new;
    case "calls":
      return copy.home_calls;
  }
}

/** One chip of the day, on Inicio and over Hoy; `active` is the part Hoy is showing. */
export function dayChipClass(active = false): string {
  return [
    "inline-flex max-w-full items-baseline gap-2 rounded-full border px-3.5 py-1.5 text-[13.5px] transition-colors duration-150",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none",
    active
      ? "border-beige/50 bg-beige/10 text-foreground"
      : "border-border bg-card text-foreground hover:border-beige/40 hover:bg-secondary/60",
  ].join(" ");
}
