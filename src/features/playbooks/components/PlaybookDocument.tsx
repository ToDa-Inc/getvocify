import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Plus } from "@phosphor-icons/react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ConfirmAction } from "@/components/ui/confirm-action";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { errorCode, playbooksApi, type EditorDoc } from "@/features/playbooks/api";
import { PlaybookObjections } from "@/features/playbooks/components/PlaybookObjections";
import { PlaybookStart } from "@/features/playbooks/components/PlaybookStart";
import { PlaybookStepRow } from "@/features/playbooks/components/PlaybookStepRow";
import { useLanguage } from "@/lib/i18n";
import {
  AUTOSAVE_MS,
  FOCUS_STEPS,
  editorFromStructure,
  publishBlocker,
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
  draftPayload,
  isLegacyBlob,
  moveStep,
  newStepKey,
  objectionsFromSnapshot,
  parsePlaybookText,
  stepsFromSnapshot,
  type EditorObjection,
  type EditorStep,
  type ObjectionCategory,
} from "@/lib/playbook-editor";
import type { MotionStatus } from "@/lib/playbook-setup";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

type Notice = { tone: "info" | "error"; text: string } | null;
type Replacement = { steps: EditorStep[]; objections: EditorObjection[]; source: PlaybookSource | null };

/**
 * One playbook as a document (plan §4.3). Reading, reviewing and editing are the same view:
 * fields look like text until focused, the draft saves itself, and there is one action,
 * Publish. A rep gets the same document read-only.
 */
export function PlaybookDocument({
  motionKey,
  canEdit,
  meta,
  template,
  insights,
  onStatus,
}: {
  motionKey: string;
  canEdit: boolean;
  /** Goal and rule lines, owned by the list. */
  meta?: ReactNode;
  template: () => EditorStep[];
  insights?: PlaybookInsights | null;
  onStatus?: (status: MotionStatus) => void;
}) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const [load, setLoad] = useState<"loading" | "error" | "ready">("loading");
  const [doc, setDoc] = useState<EditorDoc | null>(null);
  const [steps, setSteps] = useState<EditorStep[]>([]);
  const [objections, setObjections] = useState<EditorObjection[]>([]);
  const [added, setAdded] = useState<ObjectionCategory[]>([]);
  const [touched, setTouched] = useState<Set<string>>(new Set());
  const [showAll, setShowAll] = useState(false);
  const [editing, setEditing] = useState(false);
  const [started, setStarted] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [source, setSource] = useState<PlaybookSource | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [publishing, setPublishing] = useState(false);
  const [discardOpen, setDiscardOpen] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const [rebuildOpen, setRebuildOpen] = useState(false);
  const [pending, setPending] = useState<Replacement | null>(null);
  const [focusKey, setFocusKey] = useState<string | null>(null);

  // What an in-flight save needs to read without re-rendering: the latest edit and its revision.
  const latest = useRef({ steps, objections, source, updatedAt: null as string | null });
  const revision = useRef(0);
  const inflight = useRef<Promise<boolean> | null>(null);
  const statusRef = useRef(onStatus);
  statusRef.current = onStatus;
  latest.current.steps = steps;
  latest.current.objections = objections;
  latest.current.source = source;

  const adopt = useCallback((data: EditorDoc) => {
    setDoc(data);
    setSteps(stepsFromSnapshot(data));
    setObjections(objectionsFromSnapshot(data));
    setSource(data.source_doc ?? null);
    latest.current.updatedAt = data.updated_at ?? null;
    setEditing(data.source === "draft");
    setStarted(data.source !== "empty");
    setDirty(false);
    setTouched(new Set());
    setShowAll(false);
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

  /** Saves what can be saved: steps without a name yet stay on screen and wait. */
  const save = useCallback(async (): Promise<boolean> => {
    if (inflight.current) await inflight.current;
    const { steps: all, objections: answers, source: from, updatedAt } = latest.current;
    const savable = all.filter((step) => step.label.trim());
    if (savable.length === 0 || draftError(savable, answers)) return false;
    const at = revision.current;
    setSaveState("saving");
    const run = (async () => {
      try {
        const data = await playbooksApi.saveDraft(motionKey, {
          ...draftPayload(savable, answers),
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
        statusRef.current?.(data.has_live ? "published" : "draft");
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
  }, [steps, objections, dirty, editing, canEdit, saveState, save]);

  // Leaving the page or closing the row never loses the last edit.
  const flushRef = useRef<() => void>(() => undefined);
  flushRef.current = () => {
    if (dirty && editing && canEdit) void save();
  };
  useEffect(() => {
    const onHide = () => flushRef.current();
    window.addEventListener("pagehide", onHide);
    return () => {
      window.removeEventListener("pagehide", onHide);
      flushRef.current();
    };
  }, []);

  const rows = useMemo(
    () => visibleObjections(objections, insights?.objections, added),
    [objections, insights, added],
  );
  const weakest = weakestStep(insights);
  const hasLive = Boolean(doc?.has_live) || doc?.source === "published";
  const isDraft = doc?.source === "draft";
  const editable = canEdit && editing;

  const setAnswer = (category: ObjectionCategory, guidance: string) =>
    change(() =>
      setObjections((current) =>
        [...current.filter((item) => item.category !== category), { category, guidance }].sort(
          (a, b) => OBJECTION_CATEGORIES.indexOf(a.category) - OBJECTION_CATEGORIES.indexOf(b.category),
        ),
      ),
    );

  const structureNotice = (result: StructureResult, count: number): Notice => {
    if (result.fallback) return { tone: "info", text: copy.fallback };
    if (result.reason === "too_short") return { tone: "info", text: copy.reasonTooShort };
    if (result.reason === "grouped") return { tone: "info", text: copy.reasonGrouped.replace("{count}", String(count)) };
    return null;
  };

  const apply = (next: Replacement) => {
    change(() => {
      setSteps(next.steps);
      setObjections(next.objections);
      setSource(next.source);
      setAdded([]);
      setTouched(new Set());
      setShowAll(false);
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
    setNotice(structureNotice(result, next.steps.length));
    const replacement = { ...next, source: result.source };
    if (steps.some((step) => step.label.trim())) setPending(replacement);
    else apply(replacement);
  };

  const publish = async () => {
    // A step left without a name is not a step: it is dropped, not reported.
    const blocker = publishBlocker(steps.filter((step) => step.label.trim() || steps.length === 1), objections);
    if (blocker) {
      setShowAll(true);
      const errors = t.product.playbookEditorErrors as Record<string, string>;
      setNotice({ tone: "error", text: errors[blocker.code] ?? copy.publishFailed });
      if (blocker.stepIndex !== null) setFocusKey(steps[blocker.stepIndex]?.key ?? null);
      return;
    }
    setPublishing(true);
    setNotice(null);
    try {
      if (dirty || !isDraft) {
        const saved = await save();
        if (!saved) throw new Error("save");
      }
      const data = await playbooksApi.publish(motionKey);
      if (data.motions[motionKey] !== "published") throw new Error("publish");
      onStatus?.("published");
      toast.success(copy.published);
      await reload();
    } catch (error) {
      const contradiction = errorCode(error) === "contradiction";
      setNotice({ tone: "error", text: contradiction ? t.product.playbookContradiction : copy.publishFailed });
    } finally {
      setPublishing(false);
    }
  };

  const discard = async () => {
    setDiscarding(true);
    try {
      if (isDraft) adopt(await playbooksApi.discardDraft(motionKey));
      else if (doc) adopt(doc);
      setNotice(null);
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

  // Blank playbook: the start box is the whole screen.
  if (canEdit && !started && steps.length === 0) {
    return (
      <div className="space-y-4">
        {meta ? <div className="space-y-0.5">{meta}</div> : null}
        {noticeLine}
        <PlaybookStart
          motionKey={motionKey}
          onResult={onStructured}
          onTemplate={() => {
            setNotice(null);
            apply({ steps: template(), objections: [], source: null });
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
  const canPublish = editable && (dirty || isDraft);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="min-w-0 space-y-0.5">{meta}</div>
        {canEdit ? (
          <div className="flex items-center gap-3">
            {isDraft && hasLive ? <span className={THEME_TOKENS.typography.capsLabel}>{copy.draftBadge}</span> : null}
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
            {editable ? (
              <>
                {hasLive && (isDraft || dirty) ? (
                  <Button type="button" variant="ghost" size="sm" disabled={publishing} onClick={() => setDiscardOpen(true)}>
                    {copy.discard}
                  </Button>
                ) : hasLive ? (
                  <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(false)}>
                    {t.product.cancelAction}
                  </Button>
                ) : null}
                <Button type="button" size="sm" disabled={publishing || !canPublish} onClick={() => void publish()}>
                  {publishing ? (
                    <>
                      <VocifySpinner size={12} />
                      <span className="ml-1.5">{copy.publishing}</span>
                    </>
                  ) : hasLive ? (
                    copy.publishChanges
                  ) : (
                    copy.publish
                  )}
                </Button>
              </>
            ) : (
              <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(true)}>
                {copy.edit}
              </Button>
            )}
          </div>
        ) : null}
      </div>

      {noticeLine}

      {rebuildOpen ? (
        <PlaybookStart motionKey={motionKey} onResult={onStructured} onCancel={() => setRebuildOpen(false)} />
      ) : null}

      {legacy && editable ? (
        <div className="flex flex-wrap items-center gap-3 rounded-lg bg-secondary/40 p-3" role="status">
          <p className="flex-1 text-sm text-foreground">{t.product.playbookEditorLegacyBlob}</p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => apply({ steps: parsePlaybookText(steps[0]?.criterion ?? ""), objections, source })}
          >
            {t.product.playbookEditorSplit}
          </Button>
        </div>
      ) : null}

      <section className="space-y-1" aria-label={copy.steps}>
        <h3 className={THEME_TOKENS.typography.capsLabel}>{copy.steps}</h3>
        <ol>
          {steps.map((step, index) => (
            <PlaybookStepRow
              key={step.key}
              step={step}
              index={index}
              total={steps.length}
              editable={editable}
              touched={touched.has(step.key)}
              forced={showAll}
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

      <PlaybookObjections
        rows={rows}
        editable={editable}
        onAnswer={setAnswer}
        onAdd={(category) => setAdded((current) => (current.includes(category) ? current : [...current, category]))}
      />

      {(source || (editable && !rebuildOpen)) ? (
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border/40 pt-4">
          {source ? (
            <span className={THEME_TOKENS.typography.capsLabel}>
              {copy.source.replace("{name}", source.name || copy.sourceKinds[source.kind] || source.kind)}
            </span>
          ) : (
            <span />
          )}
          {editable && !rebuildOpen ? (
            <button
              type="button"
              className={cn(THEME_TOKENS.typography.capsLabel, "underline-offset-4 hover:text-foreground hover:underline")}
              onClick={() => setRebuildOpen(true)}
            >
              {copy.replaceFrom}
            </button>
          ) : null}
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
