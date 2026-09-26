import type { HomeView } from "@shared/ui/home.js";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import type { TodayItem } from "@/lib/today";

export type SectionOf<Id extends HomeView["sections"][number]["id"]> = Extract<HomeView["sections"][number], { id: Id }>;

export const paper = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card}`;
export const textAction = `px-1 py-1.5 ${THEME_TOKENS.typography.capsLabel} transition-colors hover:text-foreground`;
export const hairline = "border-[hsl(var(--hairline))]";

export const cardSelected = "border-beige/45 shadow-[0_0_0_1px_hsl(var(--beige)/0.2)]";
export const cardSelectable = `${paper} cursor-pointer transition-[border-color,box-shadow] duration-150 outline-none focus-visible:border-beige/25`;

export function undoOpen(item: TodayItem, now: number) {
  return item.undo_deadline != null && Date.parse(item.undo_deadline) >= now;
}
