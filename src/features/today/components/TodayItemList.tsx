import { Button } from "@/components/ui/button";
import type { TodayItem } from "@/lib/today";

type Props = {
  items: TodayItem[];
  onDismiss: (item: TodayItem) => void;
  onUndo: (item: TodayItem) => void;
  compact?: boolean;
};

export function TodayItemList({ items, onDismiss, onUndo, compact }: Props) {
  if (items.length === 0) return null;

  return (
    <ul className={compact ? "space-y-2" : "space-y-3"}>
      {items.map((item) => {
        const undoOpen = item.undo_deadline != null && Date.parse(item.undo_deadline) >= Date.now();
        return (
          <li
            key={item.id ?? item.dedupe_key ?? item.remote_id ?? item.reason}
            className={compact ? "rounded-lg border p-3 text-sm" : "rounded-lg border p-4"}
          >
            <p className={compact ? "text-[13px] leading-snug" : undefined}>{item.reason}</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {item.id && item.status !== "dismissed" ? (
                <Button type="button" variant="outline" size={compact ? "sm" : "default"} onClick={() => void onDismiss(item)}>
                  Descartar
                </Button>
              ) : null}
              {undoOpen ? (
                <Button type="button" variant="outline" size={compact ? "sm" : "default"} onClick={() => void onUndo(item)}>
                  Deshacer
                </Button>
              ) : null}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
