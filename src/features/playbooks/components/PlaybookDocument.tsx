import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
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
import { errorCode, playbooksApi, type EditorDoc } from "@/features/playbooks/api";
import { PlaybookObjections } from "@/features/playbooks/components/PlaybookObjections";
import { PlaybookQualification } from "@/features/playbooks/components/PlaybookQualification";
import { PlaybookStart, type SourceInput } from "@/features/playbooks/components/PlaybookStart";
import { PlaybookStepRow } from "@/features/playbooks/components/PlaybookStepRow";
import { useLanguage } from "@/lib/i18n";
import {
  AUTOSAVE_MS,
  FOCUS_STEPS,
  customObjectionId,
  editorFromStructure,
  stepRate,
  visibleObjections,
  weakestStep,
  type PlaybookInsights,
  type PlaybookSource,
  type SaveState,
  type StructureResult,
} from "@/lib/playbook-doc";
import {
  MAX_STEPS,
  OBJECTION_CATEGORIES,
  draftError,
  criteriaFromSnapshot,
  draftPayload,
  isLegacyBlob,
  moveStep,
  newStepKey,
  objectionKey,
  objectionsFromSnapshot,
  parsePlaybookText,
  stepsFromSnapshot,
  type EditorCriterion,
  type EditorObjection,
  type EditorStep,
  type ObjectionCategory,
} from "@/lib/playbook-editor";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

type Notice = { tone: "info" | "error"; text: string } | null;
type Replacement = {
  steps: EditorStep[];
  objections: EditorObjection[];
  qualification: EditorCriterion[];
  source: PlaybookSource | null;
};

/** Saves whatever is pending; resolves false when something could not be saved. */
export type Flush = () => Promise<boolean>;

/**
 * One call type's playbook as a document. Reading and editing are the same view: fields
 * look like text until focused and the changes save themselves. Turning them on for the
 * team is one action for the whole page (PlaybookList), so the document has none.
 * A rep gets the same document read-only.
 */
export function PlaybookDocument({
  motionKey,
  canEdit,
  meta,
  template,
  insights,
  onSaved,
  registerFlush,
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
}) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const [load, setLoad] = useState<"loading" | "error" | "ready">("loading");
  const [doc, setDoc] = useState<EditorDoc | null>(null);
  const [steps, setSteps] = useState<EditorStep[]>([]);
  const [objections, setObjections] = useState<EditorObjection[]>([]);
  const [qualification, setQualification] = useState<EditorCriterion[]>([]);
  const [added, setAdded] = useState<ObjectionCategory[]>([]);
  const [touched, setTouched] = useState<Set<string>>(new Set());
  const [editing, setEditing] = useState(false);
  const [started, setStarted] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [source, setSource] = useState<PlaybookSource | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [discardOpen, setDiscardOpen] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const [rebuildOpen, setRebuildOpen] = useState(false);
  const [pending, setPending] = useState<Replacement | null>(null);
  const [focusKey, setFocusKey] = useState<string | null>(null);

  // What an in-flight save reads without re-rendering: the latest edit and its revision.
  const latest = useRef({ steps, objections, qualification, source, updatedAt: null as string | null });
  const revision = useRef(0);
  const inflight = useRef<Promise<boolean> | null>(null);
  const savedRef = useRef(onSaved);
  savedRef.current = onSaved;
  latest.current.steps = steps;
  latest.current.objections = objections;
  latest.current.qualification = qualification;
  latest.current.source = source;

  const adopt = useCallback((data: EditorDoc) => {
    setDoc(data);
    setSteps(stepsFromSnapshot(data));
    setObjections(objectionsFromSnapshot(data));
    setQualification(criteriaFromSnapshot(data));
    setSource(data.source_doc ?? null);
    latest.current.updatedAt = data.updated_at ?? null;
    setEditing(data.source === "draft");
    setStarted(data.source !== "empty");
    setDirty(false);
    setTouched(new Set());
    setAdded([]);
    setSaveState("idle");
  }, []);

  const reload = useCallback(async () => {
    setLoad("loading");
    try {
      adopt(await playbooksApi.editor(motionKey));
      setLoad("ready");
    } catch {
      setLoad("error");
    }
  }, [adopt, motionKey]);

  useEffect(() => {
    setNotice(null);
    void reload();
  }, [reload]);

  const change = (next: () => void) => {
    next();
    revision.current += 1;
    setDirty(true);
    if (saveState === "saved") setSaveState("idle");
  };

  /** Saves what can be saved: a step without a name yet stays on screen and waits. */
  const save = useCallback(async (): Promise<boolean> => {
    if (inflight.current) await inflight.current;
    const { steps: all, objections: raw, qualification: rawCriteria, source: from, updatedAt } = latest.current;
    const savable = all.filter((step) => step.label.trim());
    // Rows still being named wait on screen, like a step without a name.
    const answers = raw.filter((item) => item.category !== "custom" || item.label?.trim());
    const criteria = rawCriteria.filter((item) => item.label.trim());
    if (savable.length === 0 || draftError(savable, answers, criteria)) return false;
    const at = revision.current;
    setSaveState("saving");
    const run = (async () => {
      try {
        const data = await playbooksApi.saveDraft(motionKey, {
          ...draftPayload(savable, answers, criteria),
          base_updated_at: updatedAt,
          source_id: from?.id ?? null,
        });
        latest.current.updatedAt = data.updated_at ?? null;
        setDoc(data);
        // Keep the server's step ids so a renamed step stays the same step for coaching.
        const ids = (data.steps ?? []).map((step) => step.step_id);
        setSteps((current) => {
          let i = 0;
          return current.map((step) => {
            if (!step.label.trim()) return step;
            const id = ids[i++];
            return step.step_id || !id ? step : { ...step, step_id: id };
          });
        });
        if (revision.current === at) setDirty(false);
        setSaveState("saved");
        savedRef.current?.();
        return true;
      } catch (error) {
        setSaveState(errorCode(error) === "stale_draft" ? "stale" : "error");
        return false;
      } finally {
        inflight.current = null;
      }
    })();
    inflight.current = run;
    return run;
  }, [motionKey]);

  // Autosave after a quiet moment; a failed save retries once on its own.
  useEffect(() => {
    if (!dirty || !editing || !canEdit || saveState === "stale") return;
    const timer = window.setTimeout(() => void save(), saveState === "error" ? 5000 : AUTOSAVE_MS);
    return () => window.clearTimeout(timer);
  }, [steps, objections, qualification, dirty, editing, canEdit, saveState, save]);

  // Leaving the page, closing the row or turning things on never loses the last edit.
  const flushRef = useRef<Flush>(async () => true);
  flushRef.current = async () => (dirty && editing && canEdit ? save() : true);
  useEffect(() => {
    registerFlush?.(() => flushRef.current());
    const onHide = () => void flushRef.current();
    window.addEventListener("pagehide", onHide);
    return () => {
      window.removeEventListener("pagehide", onHide);
      registerFlush?.(null);
      void flushRef.current();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const rows = useMemo(
    () => visibleObjections(objections, insights?.objections, added),
    [objections, insights, added],
  );
  const weakest = weakestStep(insights);
  const hasLive = Boolean(doc?.has_live) || doc?.source === "published";
  const isDraft = doc?.source === "draft";
  const editable = canEdit && editing;

  const patchObjection = (key: string, patch: Partial<EditorObjection>) =>
    change(() =>
      setObjections((current) => {
        const exists = current.some((item) => objectionKey(item) === key);
        if (exists) return current.map((item) => (objectionKey(item) === key ? { ...item, ...patch } : item));
        // A fixed category shown by the data or added by hand gets its entry on first edit.
        const category = key as ObjectionCategory;
        return [...current, { category, guidance: "", ...patch }].sort(
          (a, b) => OBJECTION_CATEGORIES.indexOf(a.category as ObjectionCategory) - OBJECTION_CATEGORIES.indexOf(b.category as ObjectionCategory),
        );
      }),
    );

  const addCustomObjection = () =>
    change(() =>
      setObjections((current) => {
        const taken = current.filter((item) => item.category === "custom").map((item) => item.id ?? "");
        return [{ category: "custom", id: customObjectionId("objecion", taken), label: "", trigger: "", guidance: "" }, ...current];
      }),
    );

  const removeObjection = (key: string) =>
    change(() => setObjections((current) => current.filter((item) => objectionKey(item) !== key)));

  const apply = (next: Replacement) => {
    change(() => {
      setSteps(next.steps);
      setObjections(next.objections);
      setQualification(next.qualification);
      setSource(next.source);
      setAdded([]);
      setTouched(new Set());
    });
    setStarted(true);
    setEditing(true);
    setRebuildOpen(false);
  };

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
    const replacement = { ...next, source: result.source };
    if (steps.some((step) => step.label.trim())) setPending(replacement);
    else apply(replacement);
  };

  const structure = async (input: SourceInput) =>
    onStructured(await playbooksApi.structure(motionKey, input.kind, input.payload, input.name));

  const discard = async () => {
    setDiscarding(true);
    try {
      if (isDraft) adopt(await playbooksApi.discardDraft(motionKey));
      else if (doc) adopt(doc);
      setNotice(null);
      savedRef.current?.();
    } catch {
      setNotice({ tone: "error", text: copy.saveError });
    } finally {
      setDiscarding(false);
      setDiscardOpen(false);
    }
  };

  if (load === "loading") {
    return (
      <p className="inline-flex items-center gap-2 text-sm text-muted-foreground" role="status">
        <VocifySpinner size={12} />
        {t.product.playbookEditorLoading}
      </p>
    );
  }
  if (load === "error") {
    return (
      <div className="flex items-center gap-3" role="alert">
        <p className="text-sm text-muted-foreground">{t.product.playbookEditorLoadFailed}</p>
        <Button type="button" variant="outline" size="sm" onClick={() => void reload()}>
          {t.product.retry}
        </Button>
      </div>
    );
  }

  if (!canEdit && steps.length === 0) {
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
  if (canEdit && !started && steps.length === 0) {
    return (
      <div className="space-y-4">
        {meta ? <div className="space-y-0.5">{meta}</div> : null}
        {noticeLine}
        <PlaybookStart
          submit={structure}
          onTemplate={() => {
            setNotice(null);
            apply({ steps: template(), objections: [], qualification: [], source: null });
          }}
        />
      </div>
    );
  }

  const saveLabel =
    saveState === "saving"
      ? copy.saving
      : saveState === "saved" && !dirty
        ? copy.saved
        : saveState === "error"
          ? copy.saveError
          : saveState === "stale"
            ? copy.stale
            : null;
  const legacy = isLegacyBlob(steps);
  const canDiscard = hasLive && (isDraft || dirty);

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
                  onClick={() => (saveState === "stale" ? void reload() : void save())}
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
              <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(true)}>
                {copy.edit}
              </Button>
            ) : hasLive && !canDiscard ? (
              <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(false)}>
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
                {canDiscard ? (
                  <DropdownMenuItem onSelect={() => setDiscardOpen(true)}>{copy.discard}</DropdownMenuItem>
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

      {legacy && editable ? (
        <div className="flex flex-wrap items-center gap-3 rounded-lg bg-secondary/40 p-3" role="status">
          <p className="flex-1 text-sm text-foreground">{t.product.playbookEditorLegacyBlob}</p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => apply({ steps: parsePlaybookText(steps[0]?.criterion ?? ""), objections, qualification, source })}
          >
            {t.product.playbookEditorSplit}
          </Button>
        </div>
      ) : null}

      <section className="space-y-1" aria-label={copy.checksHeading}>
        <h3 className={THEME_TOKENS.typography.capsLabel}>{copy.checksHeading}</h3>
        <ol>
          {steps.map((step, index) => (
            <PlaybookStepRow
              key={step.key}
              step={step}
              index={index}
              total={steps.length}
              editable={editable}
              touched={touched.has(step.key)}
              rate={canEdit && !editable ? stepRate(insights, step.step_id) : null}
              weakest={canEdit && !editable && Boolean(step.step_id) && step.step_id === weakest}
              autoFocus={focusKey === step.key}
              onChange={(patch) =>
                change(() => setSteps((current) => current.map((item) => (item.key === step.key ? { ...item, ...patch } : item))))
              }
              onBlur={() => setTouched((current) => (current.has(step.key) ? current : new Set(current).add(step.key)))}
              onMove={(delta) => change(() => setSteps((current) => moveStep(current, index, delta)))}
              onRemove={() => change(() => setSteps((current) => current.filter((item) => item.key !== step.key)))}
            />
          ))}
        </ol>
        {editable && steps.length < MAX_STEPS ? (
          <button
            type="button"
            className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-sm text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
            onClick={() => {
              const key = newStepKey();
              setFocusKey(key);
              change(() => setSteps((current) => [...current, { key, label: "", criterion: "" }]));
            }}
          >
            <Plus size={12} weight="light" />
            {copy.addStep}
          </button>
        ) : null}
        {editable && steps.length > FOCUS_STEPS ? (
          <p className={THEME_TOKENS.typography.capsLabel}>{copy.focusWarning}</p>
        ) : null}
      </section>

      <PlaybookQualification
        criteria={qualification}
        editable={editable}
        onChange={(next) => change(() => setQualification(next))}
      />

      <PlaybookObjections
        rows={rows}
        editable={editable}
        onChange={patchObjection}
        onAdd={(category) => setAdded((current) => (current.includes(category) ? current : [...current, category]))}
        onAddCustom={addCustomObjection}
        onRemove={removeObjection}
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
          if (pending) apply(pending);
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
