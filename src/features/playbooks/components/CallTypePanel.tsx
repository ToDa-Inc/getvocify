import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { playbooksApi } from "@/features/playbooks/api";
import { PlaybookDocument } from "@/features/playbooks/components/PlaybookDocument";
import type { Flush } from "@/features/playbooks/hooks/usePlaybookDraft";
import { callTypeIcon } from "@/features/playbooks/icons";
import { insightsKey } from "@/features/playbooks/keys";
import { PUBLISH_TONE } from "@/features/playbooks/styles";
import { useLanguage } from "@/lib/i18n";
import { publishControl, publishLabelKey, type PlaybookRow, type PublishState } from "@/lib/playbook-doc";
import type { EditorStep } from "@/lib/playbook-editor";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

/**
 * One call type on the right of "Vuestro proceso": its name and role, one sentence with where it
 * is used and what success is, and the one control its state needs: "Publicar" when never
 * published, "Publicar cambios" while changes are pending, the switch once it is live and unchanged.
 * The insights query only runs for the call type on screen.
 */
export function CallTypePanel({
  row,
  label,
  role,
  state,
  switchOn,
  canEdit,
  busy,
  deletable,
  meta,
  template,
  onPublish,
  onSwitch,
  onDelete,
  deleteLabel,
  onSaved,
  registerFlush,
}: {
  row: PlaybookRow;
  label: string;
  role: string | null;
  state: PublishState;
  switchOn: boolean | null;
  canEdit: boolean;
  busy: boolean;
  deletable: boolean;
  meta: ReactNode;
  template: () => EditorStep[];
  onPublish: () => void;
  onSwitch: (on: boolean) => void;
  onDelete: () => void;
  /** The menu's name for it: "Eliminar playbook", or "Quitar de Llamadas" when it only leaves a channel. */
  deleteLabel?: string;
  onSaved: () => void;
  registerFlush: (flush: Flush | null) => void;
}) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const insights = useQuery({
    queryKey: insightsKey(row.key),
    queryFn: () => playbooksApi.insights(row.key, "month"),
    enabled: canEdit && switchOn !== null,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
  const Icon = callTypeIcon(row.key);
  const statusText: Record<PublishState, string> = {
    live: copy.statusLive,
    changes: copy.statusChanges,
    unpublished: copy.statusUnpublished,
    paused: copy.statusPaused,
    empty: copy.statusMissing,
  };
  const control = canEdit ? publishControl(state, switchOn) : "none";
  const stateWord = (text: string) => <span className={cn("whitespace-nowrap text-[13px]", PUBLISH_TONE[state])}>{text}</span>;

  const heading = (
    <h3 className={cn(THEME_TOKENS.typography.panelTitle, "flex flex-wrap items-center gap-2.5")}>
      <Icon size={20} strokeWidth={1.5} className="text-muted-foreground" />
      {label}
      {role ? <span className="rounded-full bg-secondary px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">{role}</span> : null}
    </h3>
  );

  const publishButton = (text: string) => (
    <Button type="button" size="sm" disabled={busy} onClick={onPublish}>
      {busy ? (
        <>
          <VocifySpinner size={12} />
          <span className="ml-1.5">{copy.publishing}</span>
        </>
      ) : (
        text
      )}
    </Button>
  );

  const controls = !canEdit ? (
    stateWord(statusText[state])
  ) : control === "publish" ? (
    publishButton(copy.publish)
  ) : control === "publishChanges" ? (
    publishButton(copy[publishLabelKey(control, switchOn)])
  ) : control === "switch" && switchOn !== null ? (
    <span className="flex items-center gap-3">
      {stateWord(state === "paused" ? copy.statusPaused : copy.statusLive)}
      <Switch
        // Off has to read as "off", not as missing: the default unchecked track is near-white.
        className="data-[state=unchecked]:bg-muted-foreground/30"
        checked={switchOn}
        disabled={busy}
        aria-label={copy.switchLabel.replace("{name}", label)}
        onCheckedChange={onSwitch}
      />
    </span>
  ) : null;

  return (
    <PlaybookDocument
      motionKey={row.key}
      canEdit={canEdit}
      heading={heading}
      role={row.role === "sdr" || row.role === "ae" ? row.role : null}
      controls={controls}
      meta={meta}
      template={template}
      insights={insights.data ?? null}
      onSaved={onSaved}
      registerFlush={registerFlush}
      onDelete={deletable ? onDelete : undefined}
      deleteLabel={deleteLabel}
    />
  );
}
