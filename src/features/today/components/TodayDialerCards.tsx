import { useTodayCardActions, useTodayUndoClock } from "../hooks/useTodayCardActions";
import { TodayItemList } from "./TodayItemList";

export function TodayDialerCards() {
  const { surface, listed, dismiss, undo } = useTodayCardActions();
  useTodayUndoClock(surface.kind === "list" && listed.length > 0);

  if (surface.kind !== "list" || listed.length === 0) return null;

  return (
    <div className="mt-3 border-t border-border/40 pt-3">
      <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Hoy</p>
      <TodayItemList items={listed} onDismiss={dismiss} onUndo={undo} compact />
    </div>
  );
}
