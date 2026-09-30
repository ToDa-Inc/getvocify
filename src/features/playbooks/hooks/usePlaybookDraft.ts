import { useCallback, useEffect, useRef, useState } from "react";
import { errorCode, playbooksApi, type EditorDoc } from "@/features/playbooks/api";
import { AUTOSAVE_MS, customObjectionId, type PlaybookSource, type SaveState } from "@/lib/playbook-doc";
import {
  OBJECTION_CATEGORIES,
  criteriaFromSnapshot,
  draftError,
  draftPayload,
  moveStep as swapSteps,
  newStepKey,
  objectionKey,
  objectionsFromSnapshot,
  stepsFromSnapshot,
  type EditorCriterion,
  type EditorObjection,
  type EditorStep,
  type ObjectionCategory,
} from "@/lib/playbook-editor";

/** Saves whatever is pending; resolves false when something could not be saved. */
export type Flush = () => Promise<boolean>;

/** Everything a rebuild (document, template, legacy split) replaces at once. */
export type DraftContent = {
  steps: EditorStep[];
  objections: EditorObjection[];
  qualification: EditorCriterion[];
  source: PlaybookSource | null;
};

/**
 * One call type's draft, without markup: load the editor snapshot, keep the edits, save them
 * on a quiet moment (with the server's conflict check), flush on leave/activate, discard.
 * Edits go through named operations, so the document can't leave the draft half-changed.
 */
export function usePlaybookDraft({
  motionKey,
  canEdit,
  onSaved,
  registerFlush,
}: {
  motionKey: string;
  canEdit: boolean;
  onSaved?: () => void;
  registerFlush?: (flush: Flush | null) => void;
}) {
  const [load, setLoad] = useState<"loading" | "error" | "ready">("loading");
  const [doc, setDoc] = useState<EditorDoc | null>(null);
  const [steps, setSteps] = useState<EditorStep[]>([]);
  const [objections, setObjections] = useState<EditorObjection[]>([]);
  const [qualification, setQualification] = useState<EditorCriterion[]>([]);
  const [source, setSource] = useState<PlaybookSource | null>(null);
  /** Fixed objection categories the person added by hand (shown before they have an answer). */
  const [addedCategories, setAddedCategories] = useState<ObjectionCategory[]>([]);
  const [touched, setTouched] = useState<Set<string>>(new Set());
  const [editing, setEditing] = useState(false);
  const [started, setStarted] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [saveState, setSaveState] = useState<SaveState>("idle");

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
    setAddedCategories([]);
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
    void reload();
  }, [reload]);

  /** Every edit goes through here: it bumps the revision an in-flight save compares against. */
  const change = (edit: () => void) => {
    edit();
    revision.current += 1;
    setDirty(true);
    if (saveState === "saved") setSaveState("idle");
  };

  /** Saves what can be saved: a step, criterion or custom objection without a name waits on screen. */
  const save = useCallback(async (): Promise<boolean> => {
    if (inflight.current) await inflight.current;
    const { steps: all, objections: raw, qualification: rawCriteria, source: from, updatedAt } = latest.current;
    const savable = all.filter((step) => step.label.trim());
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

  const hasLive = Boolean(doc?.has_live) || doc?.source === "published";
  const isDraft = doc?.source === "draft";

  return {
    load,
    reload,
    hasLive,
    isDraft,
    paused: Boolean(doc?.paused),
    source,
    steps,
    objections,
    qualification,
    addedCategories,
    touched,
    editing,
    setEditing,
    started,
    dirty,
    saveState,
    save,

    touchStep: (key: string) => setTouched((current) => (current.has(key) ? current : new Set(current).add(key))),
    updateStep: (key: string, patch: Partial<EditorStep>) =>
      change(() => setSteps((current) => current.map((item) => (item.key === key ? { ...item, ...patch } : item)))),
    moveStep: (index: number, delta: -1 | 1) => change(() => setSteps((current) => swapSteps(current, index, delta))),
    removeStep: (key: string) => change(() => setSteps((current) => current.filter((item) => item.key !== key))),
    /** Appends an empty step and returns its key, so the view can focus it. */
    addStep: (): string => {
      const key = newStepKey();
      change(() => setSteps((current) => [...current, { key, label: "", criterion: "" }]));
      return key;
    },

    setCriteria: (next: EditorCriterion[]) => change(() => setQualification(next)),

    patchObjection: (key: string, patch: Partial<EditorObjection>) =>
      change(() =>
        setObjections((current) => {
          if (current.some((item) => objectionKey(item) === key)) {
            return current.map((item) => (objectionKey(item) === key ? { ...item, ...patch } : item));
          }
          // A fixed category shown by the data or added by hand gets its entry on first edit.
          return [...current, { category: key as ObjectionCategory, guidance: "", ...patch }].sort(
            (a, b) =>
              OBJECTION_CATEGORIES.indexOf(a.category as ObjectionCategory) -
              OBJECTION_CATEGORIES.indexOf(b.category as ObjectionCategory),
          );
        }),
      ),
    addCustomObjection: () =>
      change(() =>
        setObjections((current) => {
          const taken = current.filter((item) => item.category === "custom").map((item) => item.id ?? "");
          return [{ category: "custom", id: customObjectionId("objecion", taken), label: "", trigger: "", guidance: "" }, ...current];
        }),
      ),
    removeObjection: (key: string) => change(() => setObjections((current) => current.filter((item) => objectionKey(item) !== key))),
    showCategory: (category: ObjectionCategory) =>
      setAddedCategories((current) => (current.includes(category) ? current : [...current, category])),

    /** A rebuild (document, template, legacy split): everything at once, then edit mode. */
    replace: (next: DraftContent) => {
      change(() => {
        setSteps(next.steps);
        setObjections(next.objections);
        setQualification(next.qualification);
        setSource(next.source);
        setAddedCategories([]);
        setTouched(new Set());
      });
      setStarted(true);
      setEditing(true);
    },

    /** Back to the live version (the pending draft is deleted on the server). */
    discard: async (): Promise<boolean> => {
      try {
        if (isDraft) adopt(await playbooksApi.discardDraft(motionKey));
        else if (doc) adopt(doc);
        savedRef.current?.();
        return true;
      } catch {
        return false;
      }
    },
  };
}

export type PlaybookDraft = ReturnType<typeof usePlaybookDraft>;
