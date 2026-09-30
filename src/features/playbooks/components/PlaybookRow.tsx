import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { CaretRight, DotsThree } from "@phosphor-icons/react";
import { playbooksApi } from "@/features/playbooks/api";
import { PlaybookDocument } from "@/features/playbooks/components/PlaybookDocument";
import type { Flush } from "@/features/playbooks/hooks/usePlaybookDraft";
import { insightsKey } from "@/features/playbooks/keys";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Switch } from "@/components/ui/switch";
import { useLanguage } from "@/lib/i18n";
import { switchState, type PlaybookRow as Row, type RowState } from "@/lib/playbook-doc";
import type { EditorStep } from "@/lib/playbook-editor";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

const DOT: Record<Exclude<RowState, "empty">, string> = {
  live: "bg-success",
  paused: "bg-muted-foreground/40",
  pending: "bg-beige",
};

/**
 * One call type: a header that says what it is and in what state (switch, "···"), and, open,
 * its playbook as a document. One menu at a time: open with content, the document's own "···"
 * carries "Eliminar".
 */
export function PlaybookRow({
  row,
  label,
  state,
  counts,
  open,
  canEdit,
  busy,
  deletable,
  documentVersion,
  meta,
  template,
  onToggleOpen,
  onSwitch,
  onDelete,
  onSaved,
  registerFlush,
}: {
  row: Row;
  label: string;
  state: RowState;
  counts: string | null;
  open: boolean;
  canEdit: boolean;
  busy: boolean;
  deletable: boolean;
  documentVersion: number;
  meta: ReactNode;
  template: () => EditorStep[];
  onToggleOpen: () => void;
  onSwitch: (on: boolean) => void;
  onDelete: () => void;
  onSaved: () => void;
  registerFlush: (flush: Flush | null) => void;
}) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const switchOn = switchState(state);
  const statusText = state === "live" ? copy.statusLive : state === "paused" ? copy.statusPaused : copy.statusPending;

  return (
    <li className="group/row border-t border-border/40 first:border-t-0">
      <div className="flex items-center gap-2">
        <button type="button" className="flex min-w-0 flex-1 items-center gap-3 py-4 text-left" aria-expanded={open} onClick={onToggleOpen}>
          <span className="min-w-0">
            <span className="text-[15px] text-foreground">{label}</span>
            {row.role && row.role !== "any" ? (
              <span className={cn(THEME_TOKENS.typography.capsLabel, "ml-2")}>{copy.ruleRoles[row.role]}</span>
            ) : null}
            {row.unrouted && canEdit ? <span className="block text-xs text-warning">{copy.unrouted}</span> : null}
          </span>
          <span className="ml-auto flex shrink-0 items-center gap-3">
            {state === "empty" ? (
              canEdit && !open ? (
                <span className="rounded-full border border-border px-3 py-1 text-[13px] text-foreground">{copy.create}</span>
              ) : (
                <span className={THEME_TOKENS.typography.capsLabel}>{copy.statusMissing}</span>
              )
            ) : (
              <span className={cn(THEME_TOKENS.typography.capsLabel, "inline-flex items-center gap-2")}>
                <span className="hidden sm:inline">{counts}</span>
                <span className={cn("h-1.5 w-1.5 rounded-full transition-colors", DOT[state])} aria-hidden />
                {statusText}
              </span>
            )}
          </span>
        </button>
        {canEdit && switchOn !== null ? (
          <Switch
            // Off has to read as "off", not as missing: the default unchecked track is near-white.
            className="data-[state=unchecked]:bg-muted-foreground/30"
            checked={switchOn}
            disabled={busy}
            aria-label={copy.switchLabel.replace("{name}", label)}
            onCheckedChange={onSwitch}
          />
        ) : null}
        {canEdit && deletable && !(open && state !== "empty") ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                aria-label={copy.rowMenu.replace("{name}", label)}
                className={cn(
                  THEME_TOKENS.interaction.iconButton,
                  "h-8 w-8 md:opacity-0 md:group-hover/row:opacity-100 md:focus-visible:opacity-100 data-[state=open]:opacity-100",
                )}
              >
                <DotsThree size={18} weight="bold" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem className="text-destructive focus:text-destructive" onSelect={onDelete}>
                {copy.deleteAction}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
        <button type="button" tabIndex={-1} aria-hidden className="py-4" onClick={onToggleOpen}>
          <CaretRight size={14} weight="light" className={cn("text-muted-foreground transition-transform duration-150", open && "rotate-90")} />
        </button>
      </div>
      {open ? (
        <div className={cn("pb-7 pt-1", THEME_TOKENS.motion.fadeIn)}>
          <RowDocument
            key={documentVersion}
            motionKey={row.key}
            canEdit={canEdit}
            live={state === "live"}
            template={template}
            meta={meta}
            onSaved={onSaved}
            registerFlush={registerFlush}
            onDelete={deletable ? onDelete : undefined}
          />
        </div>
      ) : null}
    </li>
  );
}

/** Per open row, so the insights query only runs for the playbook on screen. */
function RowDocument({
  motionKey,
  canEdit,
  live,
  ...rest
}: {
  motionKey: string;
  canEdit: boolean;
  live: boolean;
  template: () => EditorStep[];
  meta: ReactNode;
  onSaved: () => void;
  registerFlush: (flush: Flush | null) => void;
  onDelete?: () => void;
}) {
  const insights = useQuery({
    queryKey: insightsKey(motionKey),
    queryFn: () => playbooksApi.insights(motionKey, "month"),
    enabled: canEdit && live,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
  return <PlaybookDocument motionKey={motionKey} canEdit={canEdit} insights={insights.data ?? null} {...rest} />;
}
