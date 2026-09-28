import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowDown, ArrowUp, Plus, Trash } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { IconAction } from "@/components/ui/icon-action";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { useLanguage } from "@/lib/i18n";
import { productText } from "@/lib/product-catalog";
import {
  MAX_CRITERION,
  MAX_GUIDANCE,
  MAX_LABEL,
  MAX_STEPS,
  OBJECTION_CATEGORIES,
  draftError,
  draftPayload,
  isLegacyBlob,
  moveStep,
  newStepKey,
  objectionsFromSnapshot,
  parsePlaybookText,
  stepError,
  stepsFromSnapshot,
  templateSteps,
  type EditorObjection,
  type EditorSnapshot,
  type EditorStep,
  type ObjectionCategory,
} from "@/lib/playbook-editor";
import type { MotionStatus } from "@/lib/playbook-setup";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { api, ApiError } from "@/shared/lib/api-client";

const field =
  "block w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/70 focus:outline-none focus:ring-1 focus:ring-beige/40";

type Busy = null | "loading" | "saving" | "publishing" | "importing";
type Notice = { tone: "ok" | "error"; text: string } | null;

/** Reads a file as base64 without the data: prefix. */
function fileBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const value = String(reader.result || "");
      const comma = value.indexOf(",");
      resolve(comma >= 0 ? value.slice(comma + 1) : value);
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

/**
 * The playbook of one flow as real steps and objection answers. Steps are what C04 marks
 * met/missed in every conversation; objection answers feed the pre-call brief, Team and
 * the debrief. A rep sees the live version read-only.
 */
export function PlaybookEditor({
  motionKey,
  canEdit,
  status,
  importText,
  publish,
  onStatus,
}: {
  motionKey: string;
  canEdit: boolean;
  status: MotionStatus;
  /** POST /playbooks/imports (PDF or audio) -> extracted text, or an error key. */
  importText: (kind: "pdf" | "audio", base64: string) => Promise<{ text: string | null; error: string | null }>;
  publish: () => Promise<boolean>;
  onStatus: (status: MotionStatus) => void;
}) {
  const { t, language } = useLanguage();
  const copy = t.product;
  const lang = language === "EN" ? "en" : "es";
  const [snapshot, setSnapshot] = useState<EditorSnapshot | null>(null);
  const [steps, setSteps] = useState<EditorStep[]>([]);
  const [objections, setObjections] = useState<EditorObjection[]>([]);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState<Busy>("loading");
  const [notice, setNotice] = useState<Notice>(null);
  const [pasteOpen, setPasteOpen] = useState(false);
  const [paste, setPaste] = useState("");
  const [loadFailed, setLoadFailed] = useState(false);

  const load = useCallback(async () => {
    setBusy("loading");
    setLoadFailed(false);
    try {
      const data = await api.get<EditorSnapshot>(`/playbooks/${encodeURIComponent(motionKey)}/editor`);
      setSnapshot(data);
      setSteps(stepsFromSnapshot(data));
      setObjections(objectionsFromSnapshot(data));
      setDirty(false);
    } catch {
      setLoadFailed(true);
    } finally {
      setBusy(null);
    }
  }, [motionKey]);

  useEffect(() => {
    setNotice(null);
    void load();
  }, [load]);

  const problem = useMemo(() => draftError(steps, objections), [steps, objections]);
  const legacy = isLegacyBlob(steps);
  const errorText = (code: string | null | undefined) =>
    code ? (copy.playbookEditorErrors as Record<string, string>)[code] ?? copy.playbookEditorSaveFailed : null;

  const replaceSteps = (next: EditorStep[]) => {
    if (next.length === 0) return false;
    if (steps.length > 0 && dirty && !window.confirm(copy.playbookEditorReplaceConfirm)) return false;
    setSteps(next);
    setDirty(true);
    setNotice(null);
    return true;
  };

  const edit = (index: number, patch: Partial<EditorStep>) => {
    setSteps((current) => current.map((step, i) => (i === index ? { ...step, ...patch } : step)));
    setDirty(true);
  };

  const setAnswer = (category: ObjectionCategory, guidance: string) => {
    setObjections((current) => {
      const rest = current.filter((item) => item.category !== category);
      return [...rest, { category, guidance }].sort(
        (a, b) => OBJECTION_CATEGORIES.indexOf(a.category) - OBJECTION_CATEGORIES.indexOf(b.category),
      );
    });
    setDirty(true);
  };

  const save = async (): Promise<boolean> => {
    if (problem) {
      setNotice({ tone: "error", text: errorText(problem) as string });
      return false;
    }
    setBusy("saving");
    setNotice(null);
    try {
      const data = await api.put<EditorSnapshot>(
        `/playbooks/${encodeURIComponent(motionKey)}/draft`,
        draftPayload(steps, objections),
      );
      setSnapshot(data);
      setSteps(stepsFromSnapshot(data));
      setObjections(objectionsFromSnapshot(data));
      setDirty(false);
      onStatus(status === "published" ? "published" : "draft");
      setNotice({ tone: "ok", text: copy.playbookEditorSaved });
      return true;
    } catch (error) {
      const code = error instanceof ApiError
        ? (error.data as { detail?: { code?: string } } | null | undefined)?.detail?.code
        : null;
      setNotice({ tone: "error", text: errorText(code) ?? copy.playbookEditorSaveFailed });
      return false;
    } finally {
      setBusy(null);
    }
  };

  const saveAndPublish = async () => {
    if (dirty || snapshot?.source !== "draft") {
      const saved = await save();
      if (!saved) return;
    }
    setBusy("publishing");
    setNotice(null);
    const ok = await publish();
    setBusy(null);
    if (ok) {
      setNotice({ tone: "ok", text: copy.playbookEditorPublished });
      await load();
    } else {
      setNotice({ tone: "error", text: copy.playbookEditorPublishFailed });
    }
  };

  const importFile = async (kind: "pdf" | "audio", file: File | undefined) => {
    if (!file) return;
    setBusy("importing");
    setNotice(null);
    try {
      const result = await importText(kind, await fileBase64(file));
      if (result.error) {
        setNotice({ tone: "error", text: productText(result.error, copy) || copy.playbookImportFailed });
        return;
      }
      const parsed = parsePlaybookText(result.text ?? "");
      if (!replaceSteps(parsed)) {
        if (parsed.length === 0) setNotice({ tone: "error", text: copy.playbookEditorImportEmpty });
      }
    } catch {
      setNotice({ tone: "error", text: copy.playbookImportFailed });
    } finally {
      setBusy(null);
    }
  };

  if (busy === "loading") {
    return (
      <p className="mt-3 inline-flex items-center gap-2 text-sm text-muted-foreground" role="status">
        <VocifySpinner size={12} />
        {copy.playbookEditorLoading}
      </p>
    );
  }
  if (loadFailed) {
    return (
      <div className="mt-3 flex items-center gap-3" role="alert">
        <p className="text-sm text-muted-foreground">{copy.playbookEditorLoadFailed}</p>
        <Button type="button" variant="outline" size="sm" onClick={() => void load()}>
          {copy.retry}
        </Button>
      </div>
    );
  }

  // A rep reads the live version; nothing to edit.
  if (!canEdit) {
    if (steps.length === 0) return <p className={`mt-3 ${THEME_TOKENS.typography.body}`}>{copy.playbookEditorReadOnlyEmpty}</p>;
    return (
      <div className="mt-3 space-y-4">
        <ol className="space-y-3">
          {steps.map((step, index) => (
            <li key={step.key} className="space-y-0.5">
              <p className="text-[15px] text-foreground">{index + 1}. {step.label}</p>
              {step.criterion && step.criterion !== step.label ? (
                <p className={THEME_TOKENS.typography.body}>{step.criterion}</p>
              ) : null}
              {step.example ? <p className="text-sm italic text-muted-foreground">«{step.example}»</p> : null}
            </li>
          ))}
        </ol>
        {objections.length > 0 ? (
          <div className="space-y-2">
            <p className={THEME_TOKENS.typography.capsLabel}>{copy.playbookEditorObjections}</p>
            {objections.map((item) => (
              <p key={item.category} className="text-sm text-foreground">
                <span className="text-muted-foreground">{copy.playbookObjectionCategories[item.category]}: </span>
                {item.guidance}
              </p>
            ))}
          </div>
        ) : null}
      </div>
    );
  }

  const working = busy !== null;
  const sourceLabel = snapshot?.source === "draft"
    ? copy.playbookEditorDraftPending
    : snapshot?.source === "published"
      ? copy.playbookEditorLive
      : null;

  return (
    <div className="mt-4 space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        {sourceLabel ? <span className={THEME_TOKENS.typography.capsLabel}>{sourceLabel}</span> : null}
        {dirty ? <span className={`${THEME_TOKENS.typography.capsLabel} text-beige`}>· {copy.playbookEditorUnsaved}</span> : null}
      </div>

      {/* Ways in: template, paste, PDF, audio. Every one lands in the same editable steps. */}
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" disabled={working} onClick={() => replaceSteps(templateSteps(motionKey, lang))}>
          {copy.playbookEditorTemplate}
        </Button>
        <Button type="button" variant="outline" size="sm" disabled={working} onClick={() => setPasteOpen((open) => !open)} aria-expanded={pasteOpen}>
          {copy.playbookEditorPaste}
        </Button>
        <Button type="button" variant="outline" size="sm" disabled={working} asChild>
          <label className="cursor-pointer">
            {copy.playbookImportPdf}
            <input
              type="file"
              accept="application/pdf,.pdf"
              className="sr-only"
              onChange={(event) => {
                const file = event.target.files?.[0];
                event.target.value = "";
                void importFile("pdf", file);
              }}
            />
          </label>
        </Button>
        <Button type="button" variant="outline" size="sm" disabled={working} asChild>
          <label className="cursor-pointer">
            {copy.playbookEditorImportAudio}
            <input
              type="file"
              accept="audio/*"
              className="sr-only"
              onChange={(event) => {
                const file = event.target.files?.[0];
                event.target.value = "";
                void importFile("audio", file);
              }}
            />
          </label>
        </Button>
      </div>

      {busy === "importing" ? (
        <p className="inline-flex items-center gap-2 text-sm text-muted-foreground" role="status">
          <VocifySpinner size={12} />
          {copy.playbookEditorImporting}
        </p>
      ) : null}

      {pasteOpen ? (
        <div className="space-y-2 rounded-lg bg-secondary/40 p-3">
          <p className="text-xs text-muted-foreground">{copy.playbookEditorPasteHelp}</p>
          <textarea
            className={field}
            rows={6}
            value={paste}
            placeholder={copy.playbookPastePlaceholder}
            onChange={(event) => setPaste(event.target.value)}
          />
          <Button
            type="button"
            size="sm"
            disabled={!paste.trim()}
            onClick={() => {
              if (replaceSteps(parsePlaybookText(paste))) {
                setPaste("");
                setPasteOpen(false);
              }
            }}
          >
            {copy.playbookEditorPasteApply}
          </Button>
        </div>
      ) : null}

      {legacy ? (
        <div className="flex flex-wrap items-center gap-3 rounded-lg bg-secondary/40 p-3" role="status">
          <p className="flex-1 text-sm text-foreground">{copy.playbookEditorLegacyBlob}</p>
          <Button type="button" variant="outline" size="sm" onClick={() => replaceSteps(parsePlaybookText(steps[0]?.criterion ?? ""))}>
            {copy.playbookEditorSplit}
          </Button>
        </div>
      ) : null}

      <section className="space-y-3" aria-labelledby={`steps-${motionKey}`}>
        <div>
          <h3 id={`steps-${motionKey}`} className={THEME_TOKENS.typography.capsLabel}>{copy.playbookEditorSteps}</h3>
          <p className="mt-1 text-xs text-muted-foreground">{copy.playbookEditorStepsHelp}</p>
        </div>
        {steps.length === 0 ? <p className={THEME_TOKENS.typography.body}>{copy.playbookEditorEmpty}</p> : null}
        <ol className="space-y-3">
          {steps.map((step, index) => {
            const error = stepError(step);
            return (
              <li key={step.key} className="space-y-2 rounded-lg border border-border/60 bg-background p-3">
                <div className="flex items-center gap-2">
                  <span className="w-5 shrink-0 text-sm text-muted-foreground">{index + 1}.</span>
                  <input
                    className={field}
                    value={step.label}
                    maxLength={MAX_LABEL + 20}
                    aria-label={copy.playbookEditorLabel}
                    placeholder={copy.playbookEditorLabel}
                    aria-invalid={error === "empty_label" || error === "label_too_long"}
                    onChange={(event) => edit(index, { label: event.target.value })}
                  />
                  <IconAction label={copy.playbookEditorMoveUp} disabled={index === 0} onClick={() => { setSteps((current) => moveStep(current, index, -1)); setDirty(true); }}>
                    <ArrowUp size={14} weight="light" />
                  </IconAction>
                  <IconAction label={copy.playbookEditorMoveDown} disabled={index === steps.length - 1} onClick={() => { setSteps((current) => moveStep(current, index, 1)); setDirty(true); }}>
                    <ArrowDown size={14} weight="light" />
                  </IconAction>
                  <IconAction label={copy.playbookEditorRemove} tone="danger" onClick={() => { setSteps((current) => current.filter((_, i) => i !== index)); setDirty(true); }}>
                    <Trash size={14} weight="light" />
                  </IconAction>
                </div>
                <textarea
                  className={field}
                  rows={2}
                  value={step.criterion}
                  aria-label={copy.playbookEditorCriterion}
                  placeholder={copy.playbookEditorCriterion}
                  aria-invalid={error === "criterion_too_long"}
                  onChange={(event) => edit(index, { criterion: event.target.value })}
                />
                <input
                  className={field}
                  value={step.example ?? ""}
                  aria-label={copy.playbookEditorExample}
                  placeholder={copy.playbookEditorExample}
                  onChange={(event) => edit(index, { example: event.target.value })}
                />
                {error ? <p className="text-xs text-destructive" role="alert">{errorText(error)}</p> : null}
                {!error && step.criterion.length > MAX_CRITERION * 0.9 ? (
                  <p className="text-xs text-muted-foreground">{step.criterion.length}/{MAX_CRITERION}</p>
                ) : null}
              </li>
            );
          })}
        </ol>
        {steps.length < MAX_STEPS ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              setSteps((current) => [...current, { key: newStepKey(), label: "", criterion: "" }]);
              setDirty(true);
            }}
          >
            <Plus size={14} weight="light" className="mr-1" />
            {copy.playbookEditorAddStep}
          </Button>
        ) : null}
      </section>

      <section className="space-y-3" aria-labelledby={`objections-${motionKey}`}>
        <div>
          <h3 id={`objections-${motionKey}`} className={THEME_TOKENS.typography.capsLabel}>{copy.playbookEditorObjections}</h3>
          <p className="mt-1 text-xs text-muted-foreground">{copy.playbookEditorObjectionsHelp}</p>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          {OBJECTION_CATEGORIES.map((category) => {
            const value = objections.find((item) => item.category === category)?.guidance ?? "";
            return (
              <label key={category} className="space-y-1">
                <span className="text-sm text-foreground">{copy.playbookObjectionCategories[category]}</span>
                <textarea
                  className={field}
                  rows={2}
                  value={value}
                  placeholder={copy.playbookEditorObjectionPlaceholder}
                  aria-invalid={value.length > MAX_GUIDANCE}
                  onChange={(event) => setAnswer(category, event.target.value)}
                />
              </label>
            );
          })}
        </div>
      </section>

      <div className="flex flex-wrap items-center gap-3 border-t border-border/60 pt-4">
        <Button type="button" variant="outline" size="sm" disabled={working || !dirty} onClick={() => void save()}>
          {busy === "saving" ? (
            <>
              <VocifySpinner size={12} />
              <span className="ml-1.5">{copy.playbookEditorSaving}</span>
            </>
          ) : (
            copy.playbookEditorSave
          )}
        </Button>
        <Button
          type="button"
          size="sm"
          disabled={working || Boolean(problem) || (!dirty && snapshot?.source !== "draft")}
          onClick={() => void saveAndPublish()}
        >
          {busy === "publishing" ? (
            <>
              <VocifySpinner size={12} />
              <span className="ml-1.5">{copy.playbookEditorPublishing}</span>
            </>
          ) : (
            copy.playbookPublish
          )}
        </Button>
        {notice ? (
          <p className={`text-sm ${notice.tone === "error" ? "text-destructive" : "text-muted-foreground"}`} role={notice.tone === "error" ? "alert" : "status"}>
            {notice.text}
          </p>
        ) : null}
      </div>
    </div>
  );
}
