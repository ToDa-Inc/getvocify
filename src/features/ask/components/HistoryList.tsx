import { Trash } from "@phosphor-icons/react";
import { IconAction } from "@/components/ui/icon-action";
import { groupByDay, type HistoryGroupKey } from "@/lib/ask-history";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import type { ConversationSummary } from "../hooks/useAskConversation";

const GROUP_LABEL: Record<HistoryGroupKey, string> = {
  today: "askGroupToday",
  yesterday: "askGroupYesterday",
  week: "askGroupWeek",
  older: "askGroupOlder",
};

/** Past conversations, newest first, grouped by day. The one on screen is marked; opening another is one click. */
export default function HistoryList({
  rows,
  failed,
  activeId,
  onOpen,
  onDelete,
  onClearAll,
}: {
  rows: ConversationSummary[] | null;
  failed: boolean;
  activeId: string;
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
  onClearAll: () => void;
}) {
  const { t } = useLanguage();
  const copy = t.product as Record<string, string>;
  if (rows === null) {
    return <p className={THEME_TOKENS.typography.capsLabel} role="status">{failed ? t.product.askFailed : t.product.askThinking}</p>;
  }
  if (rows.length === 0) return <p className={THEME_TOKENS.typography.body}>{t.product.askHistoryEmpty}</p>;
  return (
    <div className="space-y-6">
      {groupByDay(rows, new Date()).map((group) => (
        <section key={group.key} aria-label={copy[GROUP_LABEL[group.key]]}>
          <h3 className={`${THEME_TOKENS.typography.capsLabel} mb-1.5 px-3`}>{copy[GROUP_LABEL[group.key]]}</h3>
          <ul className="space-y-0.5">
            {group.rows.map((row) => (
              <li key={row.id} className="group flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => onOpen(row.id)}
                  aria-current={row.id === activeId ? "true" : undefined}
                  className={`min-h-10 min-w-0 flex-1 truncate rounded-lg px-3 py-2 text-left text-[15px] transition-colors hover:bg-secondary/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${row.id === activeId ? "bg-secondary/70 text-foreground" : "text-foreground/80"}`}
                >
                  {row.title || t.product.askTitle}
                </button>
                <span className="opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100 max-md:opacity-100">
                  <IconAction label={t.product.askDeleteConversation} tone="danger" onClick={() => onDelete(row.id)}>
                    <Trash size={16} weight="light" />
                  </IconAction>
                </span>
              </li>
            ))}
          </ul>
        </section>
      ))}
      <button
        type="button"
        onClick={onClearAll}
        className="rounded-md px-3 py-1 text-[13px] text-muted-foreground transition-colors hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {t.product.askClearAll}
      </button>
    </div>
  );
}
