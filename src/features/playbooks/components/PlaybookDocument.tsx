import { useMemo, useState, type ReactNode } from "react";
import { DotsThree, Plus } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { ConfirmAction } from "@/components/ui/confirm-action";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { playbooksApi } from "@/features/playbooks/api";
import { PlaybookObjections } from "@/features/playbooks/components/PlaybookObjections";
import { PlaybookQualification } from "@/features/playbooks/components/PlaybookQualification";
import { PlaybookStart, type SourceInput } from "@/features/playbooks/components/PlaybookStart";
import { PlaybookStepRow } from "@/features/playbooks/components/PlaybookStepRow";
import { usePlaybookDraft, type DraftContent, type Flush } from "@/features/playbooks/hooks/usePlaybookDraft";
import { linkButton } from "@/features/playbooks/styles";
import { useLanguage } from "@/lib/i18n";
import {
  FOCUS_STEPS,
  editorFromStructure,
  stepRate,
  visibleObjections,
  weakestStep,
  type PlaybookInsights,
  type StructureResult,
} from "@/lib/playbook-doc";
import { MAX_STEPS, isLegacyBlob, newStepKey, parsePlaybookText, type EditorStep } from "@/lib/playbook-editor";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

export type { Flush } from "@/features/playbooks/hooks/usePlaybookDraft";

type Notice = { tone: "info" | "error"; text: string } | null;

/**
 * One call type's playbook as a document. Reading and editing are the same view: fields
 * look like text until focused and the changes save themselves (usePlaybookDraft). Turning
 * them on for the team is one action for the whole page (PlaybookList), so the document has
 * none. A rep gets the same document read-only.
 */
export function PlaybookDocument({
  motionKey,
  canEdit,
  meta,
  template,
  insights,
  onSaved,
  registerFlush,
  onDelete,
}: {
  motionKey: string;
  canEdit: boolean;
  /** Goal (and, when it matters, the rule), owned by the list. */
  meta?: ReactNode;
  template: () => EditorStep[];
  insights?: PlaybookInsights | null;
  /** A draft was saved or discarded: the list refreshes its counts and pending state. */
  onSaved?: () => void;
  /** The list calls this before turning drafts on, so nothing typed is left behind. */
  registerFlush?: (flush: Flush | null) => void;
  /** "Eliminar playbook", owned by the list; shown in this document's "···" menu. */
  onDelete?: () => void;
}) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const draft = usePlaybookDraft({ motionKey, canEdit, onSaved, registerFlush });
  const [notice, setNotice] = useState<Notice>(null);
  const [discardOpen, setDiscardOpen] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const [rebuildOpen, setRebuildOpen] = useState(false);
  const [pending, setPending] = useState<DraftContent | null>(null);
  const [focusKey, setFocusKey] = useState<string | null>(null);

  const rows = useMemo(
    () => visibleObjections(draft.objections, insights?.objections, draft.addedCategories),
    [draft.objections, insights, draft.addedCategories],
  );
  const weakest = weakestStep(insights);
  const editable = canEdit && draft.editing;

  const replace = (next: DraftContent) => {
    draft.replace(next);
    setRebuildOpen(false);
  };

  /** A document or audio came back structured: say how, then replace (asking if there is content). */
  const onStructured = (result: StructureResult) => {
    const next = editorFromStructure(result, newStepKey);
    if (next.steps.length === 0) {
      setNotice({ tone: "error", text: copy.reasonNoProcess });
      return;
    }
    setNotice(
      result.fallback
        ? { tone: "info", text: copy.fallback }
        : result.reason === "too_short"
          ? { tone: "info", text: copy.reasonTooShort }
          : result.reason === "grouped"
            ? { tone: "info", text: copy.reasonGrouped.replace("{count}", String(next.steps.length)) }
            : null,
    );
    const content = { ...next, source: result.source };
    if (draft.steps.some((step) => step.label.trim())) setPending(content);
    else replace(content);
  };

  const structure = async (input: SourceInput) =>
    onStructured(await playbooksApi.structure(motionKey, input.kind, input.payload, input.name));

  const discard = async () => {
    setDiscarding(true);
    const ok = await draft.discard();
    setNotice(ok ? null : { tone: "error", text: copy.saveError });
    setDiscarding(false);
    setDiscardOpen(false);
  };

  if (draft.load === "loading") {
    return (
      <p className="inline-flex items-center gap-2 text-sm text-muted-foreground" role="status">
        <VocifySpinner size={12} />
        {t.product.playbookEditorLoading}
      </p>
    );
  }
  if (draft.load === "error") {
    return (
      <div className="flex items-center gap-3" role="alert">
        <p className="text-sm text-muted-foreground">{t.product.playbookEditorLoadFailed}</p>
        <Button type="button" variant="outline" size="sm" onClick={() => void draft.reload()}>
          {t.product.retry}
        </Button>
      </div>
    );
  }
  if (!canEdit && draft.steps.length === 0) {
    return <p className={THEME_TOKENS.typography.body}>{t.product.playbookEditorReadOnlyEmpty}</p>;
  }

  const noticeLine = notice ? (
    <p
      className={cn("text-sm", notice.tone === "error" ? "text-destructive" : "text-muted-foreground")}
      role={notice.tone === "error" ? "alert" : "status"}
    >
      {notice.text}
    </p>
  ) : null;

  // Blank call type: the start box is all there is.
  if (canEdit && !draft.started && draft.steps.length === 0) {
    return (
      <div className="space-y-4">
        {meta ? <div className="space-y-0.5">{meta}</div> : null}
        {noticeLine}
        <PlaybookStart
          submit={structure}
          onTemplate={() => {
            setNotice(null);
            replace({ steps: template(), objections: [], qualification: [], source: null });
          }}
        />
      </div>
    );
  }

  const { saveState } = draft;
  const saveLabel =
    saveState === "saving"
      ? copy.saving
      : saveState === "saved" && !draft.dirty
        ? copy.saved
        : saveState === "error"
          ? copy.saveError
          : saveState === "stale"
            ? copy.stale
            : null;
  const canDiscard = draft.hasLive && (draft.isDraft || draft.dirty);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div className="min-w-0 space-y-0.5">{meta}</div>
        {canEdit ? (
          <div className="flex items-center gap-2">
            {saveLabel ? (
              saveState === "error" || saveState === "stale" ? (
                <button
                  type="button"
                  className={cn(THEME_TOKENS.typography.capsLabel, "text-warning underline-offset-4 hover:underline")}
                  onClick={() => (saveState === "stale" ? void draft.reload() : void draft.save())}
                >
                  {saveLabel}
                </button>
              ) : (
                <span className={THEME_TOKENS.typography.capsLabel} role="status">
                  {saveLabel}
                </span>
              )
            ) : null}
            {!editable ? (
              <Button type="button" variant="ghost" size="sm" onClick={() => draft.setEditing(true)}>
                {copy.edit}
              </Button>
            ) : draft.hasLive && !canDiscard ? (
              <Button type="button" variant="ghost" size="sm" onClick={() => draft.setEditing(false)}>
                {copy.done}
              </Button>
            ) : null}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button type="button" aria-label={copy.more} className={THEME_TOKENS.interaction.iconButton}>
                  <DotsThree size={18} weight="bold" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onSelect={() => setRebuildOpen(true)}>{copy.replaceFrom}</DropdownMenuItem>
                {canDiscard ? <DropdownMenuItem onSelect={() => setDiscardOpen(true)}>{copy.discard}</DropdownMenuItem> : null}
                {onDelete ? (
                  <DropdownMenuItem className="text-destructive focus:text-destructive" onSelect={onDelete}>
                    {copy.deleteAction}
                  </DropdownMenuItem>
                ) : null}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        ) : null}
      </div>

      {noticeLine}

      {rebuildOpen ? (
        <div className={THEME_TOKENS.motion.fadeIn}>
          <PlaybookStart submit={structure} onCancel={() => setRebuildOpen(false)} />
        </div>
      ) : null}

      {isLegacyBlob(draft.steps) && editable ? (
        <div className="flex flex-wrap items-center gap-3 rounded-lg bg-secondary/40 p-3" role="status">
          <p className="flex-1 text-sm text-foreground">{t.product.playbookEditorLegacyBlob}</p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() =>
              replace({
                steps: parsePlaybookText(draft.steps[0]?.criterion ?? ""),
                objections: draft.objections,
                qualification: draft.qualification,
                source: draft.source,
              })
            }
          >
            {t.product.playbookEditorSplit}
          </Button>
        </div>
      ) : null}

      <section className="space-y-1" aria-label={copy.checksHeading}>
        <h3 className={THEME_TOKENS.typography.capsLabel}>{copy.checksHeading}</h3>
        <ol>
          {draft.steps.map((step, index) => (
            <PlaybookStepRow
              key={step.key}
              step={step}
              index={index}
              total={draft.steps.length}
              editable={editable}
              touched={draft.touched.has(step.key)}
              rate={canEdit && !editable ? stepRate(insights, step.step_id) : null}
              weakest={canEdit && !editable && Boolean(step.step_id) && step.step_id === weakest}
              autoFocus={focusKey === step.key}
              onChange={(patch) => draft.updateStep(step.key, patch)}
              onBlur={() => draft.touchStep(step.key)}
              onMove={(delta) => draft.moveStep(index, delta)}
              onRemove={() => draft.removeStep(step.key)}
            />
          ))}
        </ol>
        {editable && draft.steps.length < MAX_STEPS ? (
          <button type="button" className={linkButton} onClick={() => setFocusKey(draft.addStep())}>
            <Plus size={12} weight="light" />
            {copy.addStep}
          </button>
        ) : null}
        {editable && draft.steps.length > FOCUS_STEPS ? <p className={THEME_TOKENS.typography.capsLabel}>{copy.focusWarning}</p> : null}
      </section>

      <PlaybookQualification criteria={draft.qualification} editable={editable} onChange={draft.setCriteria} />

      <PlaybookObjections
        rows={rows}
        editable={editable}
        onChange={draft.patchObjection}
        onAdd={draft.showCategory}
        onAddCustom={draft.addCustomObjection}
        onRemove={draft.removeObjection}
      />

      <ConfirmAction
        open={pending !== null}
        onOpenChange={(open) => {
          if (!open) setPending(null);
        }}
        title={t.product.playbookEditorReplaceTitle}
        description={t.product.playbookEditorReplaceConfirm}
        confirmLabel={t.product.playbookEditorReplaceAction}
        cancelLabel={t.product.cancelAction}
        tone="default"
        onConfirm={() => {
          if (pending) replace(pending);
          setPending(null);
        }}
      />
      <ConfirmAction
        open={discardOpen}
        onOpenChange={setDiscardOpen}
        title={copy.discardTitle}
        description={copy.discardConfirm}
        confirmLabel={copy.discard}
        cancelLabel={t.product.cancelAction}
        tone="danger"
        pending={discarding}
        onConfirm={() => void discard()}
      />
    </div>
  );
}
