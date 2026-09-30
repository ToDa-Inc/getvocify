import { useMemo, useState, type ReactNode } from "react";
import { ChatsCircle, DotsThree, ListNumbers, Plus, Target } from "@phosphor-icons/react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ConfirmAction } from "@/components/ui/confirm-action";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { TabCount, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { playbooksApi, type FillScope, type FillSource } from "@/features/playbooks/api";
import { CompleteButton } from "@/features/playbooks/components/DocParts";
import { FillBox } from "@/features/playbooks/components/FillBox";
import { PlaybookObjections } from "@/features/playbooks/components/PlaybookObjections";
import { PlaybookQualification } from "@/features/playbooks/components/PlaybookQualification";
import { PlaybookStart, type SourceInput } from "@/features/playbooks/components/PlaybookStart";
import { PlaybookStepRow } from "@/features/playbooks/components/PlaybookStepRow";
import { SaveStatus } from "@/features/playbooks/components/SaveStatus";
import { usePlaybookDraft, type DraftContent, type Flush } from "@/features/playbooks/hooks/usePlaybookDraft";
import { useDismissed } from "@/features/playbooks/hooks/useDismissed";
import { linkButton } from "@/features/playbooks/styles";
import { useLanguage } from "@/lib/i18n";
import {
  FOCUS_STEPS,
  editorFromStructure,
  isSuggestion,
  needsCriterion,
  stepRate,
  visibleObjections,
  weakestStep,
  type ObjectionRow,
  type PlaybookInsights,
  type StructureResult,
} from "@/lib/playbook-doc";
import {
  MAX_STEPS,
  draftPayload,
  isLegacyBlob,
  messySteps,
  newStepKey,
  stepsAsText,
  parsePlaybookText,
  type EditorCriterion,
  type EditorStep,
  type ObjectionCategory,
} from "@/lib/playbook-editor";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

export type { Flush } from "@/features/playbooks/hooks/usePlaybookDraft";

type Notice = { tone: "info" | "error"; text: string } | null;
type Tab = "steps" | "qualification" | "objections";

/** A small dot on a tab that has something to fix (a step without "counts as done", an unanswered objection). */
function Attention({ on, label }: { on: boolean; label: string }) {
  if (!on) return null;
  return <span className="h-1.5 w-1.5 rounded-full bg-warning" title={label} aria-label={label} />;
}

/**
 * One call type's playbook: a header (owned by the panel), the one line where the manager tells
 * Vocify what to change, and three tabs, one per layer: the steps Vocify checks, what the call
 * has to find out, and the answers to objections. Everything reads as sentences and is edited
 * where it is read; what is missing Vocify writes on request. Changes save themselves as a draft
 * and reach the team when the panel publishes them. A rep reads the same view.
 */
export function PlaybookDocument({
  motionKey,
  canEdit,
  heading,
  role = null,
  controls,
  meta,
  template,
  insights,
  onSaved,
  registerFlush,
  onDelete,
}: {
  motionKey: string;
  canEdit: boolean;
  /** Name and role, owned by the panel. */
  heading?: ReactNode;
  /** The call type's role: which qualification methods are offered. */
  role?: "sdr" | "ae" | null;
  /** The panel's state and actions (status, publish, switch), next to the document's menu. */
  controls?: ReactNode;
  /** Where it is used and what success is, owned by the list. */
  meta?: ReactNode;
  template: () => EditorStep[];
  insights?: PlaybookInsights | null;
  /** A draft was saved or discarded: the list refreshes its state. */
  onSaved?: () => void;
  /** The list calls this before publishing, so nothing typed is left behind. */
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
  const [tab, setTab] = useState<Tab>("steps");
  // What Vocify is writing: the whole request ("box") or one item's missing part (its key).
  const [filling, setFilling] = useState<string | null>(null);
  const dismissed = useDismissed(`playbook:${motionKey}`);

  const rows = useMemo(
    () => visibleObjections(draft.objections, insights?.objections, draft.addedCategories),
    [draft.objections, insights, draft.addedCategories],
  );
  const weakest = weakestStep(insights);
  const editable = canEdit;

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

  const snapshot = (): DraftContent => ({
    steps: draft.steps,
    objections: draft.objections,
    qualification: draft.qualification,
    source: draft.source,
  });
  // What is sent as `current`: a scope's indexes point into these lists.
  const savableSteps = draft.steps.filter((step) => step.label.trim());
  const savableCriteria = draft.qualification.filter((item) => item.label.trim());

  /**
   * "Dile a Vocify": the request and what is on screen go to Vocify, the answer becomes the
   * draft (it saves itself, nothing reaches the team until published) and one toast says what
   * changed, with an undo. With a scope ("Completar" on one item) only that item can change.
   * Throws, so the box can say why.
   */
  const fill = async (source: FillSource, target: string, scope?: FillScope) => {
    const before = snapshot();
    setFilling(target);
    try {
      const current = draftPayload(savableSteps, before.objections, savableCriteria);
      const result = await playbooksApi.fill(motionKey, source, current, scope);
      if (!result.changes) {
        toast(result.summary || copy.fillNothing);
        return;
      }
      draft.replace({ ...editorFromStructure(result, newStepKey), source: before.source });
      toast(result.summary || copy.fillDone, { action: { label: copy.undo, onClick: () => draft.replace(before) } });
    } finally {
      setFilling(null);
    }
  };
  /** A "Completar" button: the request is written for the manager, scoped to its item. */
  const ask = (request: string, target: string, scope: FillScope) => {
    void fill({ kind: "text", payload: request }, target, scope).catch(() => toast.error(copy.fillFailed));
  };
  const completeStep = (step: EditorStep) => {
    const n = savableSteps.indexOf(step) + 1;
    ask(copy.reqCriterion.replace("{n}", String(n)).replace("{label}", step.label), step.key, { steps: [n] });
  };
  const completeCriterion = (item: EditorCriterion) =>
    ask(copy.reqGood.replace("{label}", item.label), item.key, { qualification: [savableCriteria.indexOf(item) + 1] });
  const completeObjection = (row: ObjectionRow) => {
    const { category, label } = row.objection;
    const name =
      category === "custom" ? label ?? "" : row.objection.trigger?.trim() || copy.objectionSays[category] || category;
    ask(copy.reqAnswer.replace("{label}", name), row.key, {
      objections: [{ category, ...(category === "custom" ? { label: label ?? "" } : {}) }],
    });
  };

  /**
   * Steps an import split badly (a name that is only a number, a name cut mid-word): Vocify
   * structures them again from their own text, like a new import of just the steps. Objections
   * and qualification stay as they are; one toast with an undo.
   */
  const tidySteps = async () => {
    const before = snapshot();
    setFilling("tidy");
    try {
      const result = await playbooksApi.structure(motionKey, "text", stepsAsText(savableSteps));
      const next = editorFromStructure(result, newStepKey);
      if (next.steps.length === 0) {
        toast(copy.fillNothing);
        return;
      }
      draft.replace({ ...before, steps: next.steps });
      toast(copy.tidied.replace("{count}", String(next.steps.length)), {
        action: { label: copy.undo, onClick: () => draft.replace(before) },
      });
    } catch {
      toast.error(copy.fillFailed);
    } finally {
      setFilling(null);
    }
  };

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

  const canDiscard = draft.hasLive && (draft.isDraft || draft.dirty);
  const menu = (items: { label: string; onSelect: () => void; danger?: boolean }[]) =>
    items.length ? (
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button type="button" aria-label={copy.more} className={THEME_TOKENS.interaction.iconButton}>
            <DotsThree size={18} weight="bold" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          {items.map((item) => (
            <DropdownMenuItem
              key={item.label}
              className={item.danger ? "text-destructive focus:text-destructive" : undefined}
              onSelect={item.onSelect}
            >
              {item.label}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    ) : null;
  const deleteItem = onDelete ? [{ label: copy.deleteAction, onSelect: onDelete, danger: true }] : [];

  const header = (right: ReactNode) => (
    // The title keeps a readable minimum; when the actions don't fit beside it they wrap below it.
    <div className="flex flex-col-reverse gap-2 sm:flex-row sm:flex-wrap sm:items-start sm:justify-between sm:gap-x-4 sm:gap-y-2">
      <div className="min-w-0 flex-1 basis-56 space-y-1">
        {heading}
        {meta}
      </div>
      <div className="flex shrink-0 items-center gap-2 self-end sm:ml-auto sm:self-start">{right}</div>
    </div>
  );

  // Blank call type: the start box is all there is.
  if (canEdit && !draft.started && draft.steps.length === 0) {
    return (
      <div className="space-y-5">
        {header(
          <>
            {controls}
            {canEdit ? menu(deleteItem) : null}
          </>,
        )}
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

  const unanswered = rows.some((row) => isSuggestion(row, draft.addedCategories) && !dismissed.has(row.key));
  const objectionCount = rows.filter((row) => row.objection.guidance.trim()).length;

  return (
    <div className="space-y-5">
      {header(
        <>
          {canEdit ? (
            <SaveStatus state={draft.saveState} dirty={draft.dirty} onRetry={() => void draft.save()} onReload={() => void draft.reload()} />
          ) : null}
          {controls}
          {canEdit
            ? menu([
                { label: copy.replaceFrom, onSelect: () => setRebuildOpen(true) },
                ...(canDiscard ? [{ label: copy.discard, onSelect: () => setDiscardOpen(true) }] : []),
                ...deleteItem,
              ])
            : null}
        </>,
      )}

      {noticeLine}

      {rebuildOpen ? (
        <div className={THEME_TOKENS.motion.fadeIn}>
          <PlaybookStart submit={structure} onCancel={() => setRebuildOpen(false)} />
        </div>
      ) : null}

      {isLegacyBlob(draft.steps) && editable ? (
        <div className={cn("flex flex-wrap items-center gap-3 bg-secondary/40 p-3", THEME_TOKENS.radius.control)} role="status">
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

      {editable && messySteps(savableSteps) > 0 ? (
        <div className={cn("flex flex-wrap items-center gap-3 bg-beige/10 px-4 py-2.5", THEME_TOKENS.radius.control)} role="status">
          <p className="min-w-0 flex-1 text-sm text-foreground">{copy.messySteps}</p>
          <CompleteButton label={copy.tidySteps} pending={filling === "tidy"} disabled={filling !== null} onClick={() => void tidySteps()} />
        </div>
      ) : null}

      <Tabs value={tab} onValueChange={(value) => setTab(value as Tab)}>
        <TabsList aria-label={copy.checksHeading}>
          <TabsTrigger value="steps">
            <ListNumbers size={15} weight="light" />
            {copy.blocks.steps}
            <TabCount value={draft.steps.length} />
            <Attention on={editable && draft.steps.some((step) => step.label.trim() && needsCriterion(step))} label={copy.attentionSteps} />
          </TabsTrigger>
          {editable || draft.qualification.length > 0 ? (
            <TabsTrigger value="qualification">
              <Target size={15} weight="light" />
              {copy.blocks.qualification}
              <TabCount value={draft.qualification.length} />
            </TabsTrigger>
          ) : null}
          {editable || objectionCount > 0 ? (
            <TabsTrigger value="objections">
              <ChatsCircle size={15} weight="light" />
              {copy.blocks.objections}
              <TabCount value={objectionCount} />
              <Attention on={editable && unanswered} label={copy.attentionObjections} />
            </TabsTrigger>
          ) : null}
        </TabsList>

        <TabsContent value="steps">
          <ol>
            {draft.steps.map((step, index) => (
              <PlaybookStepRow
                key={step.key}
                step={step}
                index={index}
                total={draft.steps.length}
                editable={editable}
                touched={draft.touched.has(step.key)}
                rate={canEdit ? stepRate(insights, step.step_id) : null}
                weakest={canEdit && Boolean(step.step_id) && step.step_id === weakest}
                autoFocus={focusKey === step.key}
                completing={filling === step.key}
                busy={filling !== null}
                onComplete={() => completeStep(step)}
                onChange={(patch) => draft.updateStep(step.key, patch)}
                onBlur={() => draft.touchStep(step.key)}
                onMove={(delta) => draft.moveStep(index, delta)}
                onRemove={() => draft.removeStep(step.key)}
              />
            ))}
          </ol>
          <div className="flex flex-wrap items-center gap-3 pt-1">
            {editable && draft.steps.length < MAX_STEPS ? (
              <button type="button" className={linkButton} onClick={() => setFocusKey(draft.addStep())}>
                <Plus size={12} weight="light" />
                {copy.addStep}
              </button>
            ) : null}
            {editable && draft.steps.length > FOCUS_STEPS ? <p className="text-xs text-warning">{copy.focusWarning}</p> : null}
          </div>
        </TabsContent>

        <TabsContent value="qualification">
          <PlaybookQualification
            criteria={draft.qualification}
            editable={editable}
            role={role}
            completingKey={filling}
            busy={filling !== null}
            onComplete={completeCriterion}
            onChange={draft.setCriteria}
          />
        </TabsContent>

        <TabsContent value="objections">
          <PlaybookObjections
            rows={rows}
            added={draft.addedCategories}
            dismissed={[...dismissed.keys]}
            editable={editable}
            completingKey={filling}
            busy={filling !== null}
            onComplete={completeObjection}
            onChange={draft.patchObjection}
            onAdd={draft.showCategory}
            onAddCustom={draft.addCustomObjection}
            onRemove={draft.removeObjection}
            onDismiss={dismissed.add}
          />
        </TabsContent>
      </Tabs>

      {canEdit && !rebuildOpen ? (
        // Floats at the bottom of the screen: the list scrolls under it (glass), always one step away.
        <div className="sticky bottom-4 z-10 pt-2">
          <FillBox placeholder={copy.fillPlaceholder} busy={filling !== null} submit={(source) => fill(source, "box")} />
        </div>
      ) : null}

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
