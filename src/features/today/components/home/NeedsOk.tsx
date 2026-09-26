import { useEffect, useId, useRef, useState } from "react";
import { CaretDown } from "@phosphor-icons/react";
import { NEEDS_OK_VISIBLE, type HomeNeedsOkRow } from "@shared/ui/home.js";
import { Button } from "@/components/ui/button";
import type { ProductTranslations } from "@/lib/product-catalog";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import type { TodayItem } from "@/lib/today";
import { paper, textAction, undoOpen, type SectionOf } from "./shared";

type Actions = {
  now: number;
  copy: ProductTranslations;
  onConfirm: (item: TodayItem) => void;
  onUndo: (item: TodayItem) => void;
  onOpen: (memoId: string) => void;
};

function ConfirmRow({ item, now, copy, onConfirm, onUndo, onOpen }: Actions & { item: TodayItem }) {
  const settled = item.status != null && item.status !== "pending";
  return (
    <div className="flex min-h-[50px] items-center gap-4 px-[18px] py-3">
      <div className="min-w-0 flex-1">
        <p className="text-[14.5px] leading-normal text-foreground">{item.reason}</p>
        {item.detail ? <p className={`mt-px truncate leading-normal ${THEME_TOKENS.typography.capsLabel}`}>{item.detail}</p> : null}
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        {settled ? (
          undoOpen(item, now) ? (
            <button type="button" className={textAction} onClick={() => onUndo(item)}>{copy.undo}</button>
          ) : null
        ) : (
          <>
            <Button type="button" variant="outline" className="h-8 px-3.5 text-[13.5px]" onClick={() => onConfirm(item)}>
              {copy.confirmAction}
            </Button>
            {item.memo_id ? (
              <button type="button" className={textAction} onClick={() => onOpen(item.memo_id as string)}>{copy.home_review}</button>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}

function ConfirmGroup({ entry, ...actions }: Actions & { entry: Extract<HomeNeedsOkRow, { kind: "confirm_group" }> }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="divide-y divide-border/60">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        data-state={open ? "open" : "closed"}
        className="group flex min-h-[50px] w-full items-center gap-4 px-[18px] py-3 text-left text-[14.5px] leading-normal text-foreground"
      >
        <span className="min-w-0 flex-1">{actions.copy.home_confirm_group.replace("{count}", String(entry.count))}</span>
        <CaretDown size={14} weight="light" className="shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-180" />
      </button>
      {open ? entry.items.map((item) => <ConfirmRow key={item.id ?? item.dedupe_key ?? item.reason} item={item} {...actions} />) : null}
    </div>
  );
}

function PlainRow({ entry, copy, onOpen }: Pick<Actions, "copy" | "onOpen"> & { entry: Extract<HomeNeedsOkRow, { kind: "followup" | "review" }> }) {
  const name = entry.name || copy.today_unknown_contact;
  const line = entry.kind === "followup" ? copy.home_followup_row.replace("{name}", name) : copy.home_review_row.replace("{name}", name);
  let tail: string | null = null;
  if (entry.kind === "followup") {
    if (entry.status === "generating") tail = copy.home_followup_writing;
    else if (entry.status === "unavailable") tail = copy.home_followup_failed;
    else if (entry.subject) tail = copy.home_followup_subject.replace("{subject}", entry.subject);
  }
  return (
    <div className="flex min-h-[50px] items-center gap-4 px-[18px] py-3">
      <p className="min-w-0 flex-1 truncate text-[14.5px] leading-normal text-foreground">
        {line}
        {tail ? <span className="text-muted-foreground"> · {tail}</span> : null}
      </p>
      {entry.action ? (
        <button type="button" className={`shrink-0 ${textAction}`} onClick={() => onOpen(entry.memoId)}>
          {entry.action === "review" ? copy.home_review : copy.home_open}
        </button>
      ) : null}
    </div>
  );
}

function rowKey(entry: HomeNeedsOkRow) {
  if (entry.kind === "confirm") return entry.item.id ?? entry.item.dedupe_key ?? entry.item.reason;
  if (entry.kind === "confirm_group") return "confirm-group";
  return `${entry.kind}:${entry.memoId}`;
}

export function NeedsOk({ section, ...actions }: Actions & { section: SectionOf<"needs_ok"> }) {
  const listId = useId();
  const [expanded, setExpanded] = useState(false);
  const revealed = useRef<HTMLDivElement>(null);
  const rows = expanded ? section.rows : section.shown;

  useEffect(() => {
    if (expanded) revealed.current?.focus();
  }, [expanded]);

  return (
    <>
      <div id={listId} className={`${paper} divide-y divide-border/60`}>
        {rows.map((entry, index) => {
          const first = expanded && index === NEEDS_OK_VISIBLE;
          return (
            <div
              key={rowKey(entry)}
              ref={first ? revealed : undefined}
              tabIndex={first ? -1 : undefined}
              className="outline-none focus-visible:bg-secondary/40"
            >
              {entry.kind === "confirm" ? (
                <ConfirmRow item={entry.item} {...actions} />
              ) : entry.kind === "confirm_group" ? (
                <ConfirmGroup entry={entry} {...actions} />
              ) : (
                <PlainRow entry={entry} copy={actions.copy} onOpen={actions.onOpen} />
              )}
            </div>
          );
        })}
      </div>
      {!expanded && section.more > 0 ? (
        <button
          type="button"
          aria-expanded={false}
          aria-controls={listId}
          className={`mx-0.5 mt-2.5 ${THEME_TOKENS.typography.capsLabel} transition-colors hover:text-foreground`}
          onClick={() => setExpanded(true)}
        >
          {actions.copy.today_folded.replace("{count}", String(section.more))}
        </button>
      ) : null}
    </>
  );
}
