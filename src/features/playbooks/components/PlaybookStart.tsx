import { useRef, useState } from "react";
import { FileText, Paperclip, X } from "lucide-react";
import VoiceComposer from "@/features/ask/components/VoiceComposer";
import { blobBase64, errorCode, playbooksApi } from "@/features/playbooks/api";
import { Button } from "@/components/ui/button";
import { IconAction } from "@/components/ui/icon-action";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { useLanguage } from "@/lib/i18n";
import { appendDictation, sourceKindForFile, type SourceKind } from "@/lib/playbook-doc";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

export type SourceInput = { kind: SourceKind; payload: string; name?: string };

/** Files taken at once when the box accepts several (the API takes the same number). */
export const MAX_FILES = 8;

/**
 * The one box a playbook starts from: write, paste, dictate or drop a file. The owner decides
 * where it goes (the whole company, or one call type); this box only gathers the source and
 * shows one steady state while Vocify reads it.
 */
export function PlaybookStart({
  submit,
  placeholder,
  readingLabel,
  onTemplate,
  onCancel,
  minHeight = "min-h-[152px]",
  multiple = false,
  submitMany,
  manyReadingLabel,
  manyHint,
}: {
  /** Throws on failure; an ApiError's detail.code becomes the message. */
  submit: (source: SourceInput) => Promise<void>;
  placeholder?: string;
  readingLabel?: string;
  /** The box takes up to MAX_FILES files at once (and the pasted text too) and hands them all to `submitMany`. */
  multiple?: boolean;
  submitMany?: (sources: SourceInput[]) => Promise<void>;
  /** "Leyendo {total} archivos…" while several are read. */
  manyReadingLabel?: string;
  /** A line under the box: what to give first ("Empieza por vuestro guion de ventas"). */
  manyHint?: string;
  onTemplate?: () => void;
  onCancel?: () => void;
  minHeight?: string;
}) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  // One file replaces the box; several sit under it as chips.
  const file = multiple ? null : (files[0] ?? null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const take = async (picked: File[]) => {
    setError(null);
    for (const one of multiple ? picked : picked.slice(0, 1)) {
      const kind = sourceKindForFile(one);
      if (!kind) {
        setError(copy.startUnsupported);
        continue;
      }
      if (kind === "text") {
        // A text file is just text: show it, so it can be read and trimmed first.
        const body = await one.text();
        setText((current) => appendDictation(current, body));
        continue;
      }
      setFiles((current) => (multiple ? [...current, one].slice(0, MAX_FILES) : [one]));
    }
  };

  const create = async () => {
    if (multiple && submitMany) {
      if (!files.length && !text.trim()) return;
      setBusy(true);
      setError(null);
      try {
        const sources: SourceInput[] = text.trim() ? [{ kind: "text", payload: text.trim() }] : [];
        for (const one of files) {
          const kind = sourceKindForFile(one);
          if (kind) sources.push({ kind, payload: await blobBase64(one), name: one.name });
        }
        await submitMany(sources);
      } catch (caught) {
        const code = errorCode(caught);
        setError((code && copy.readErrors[code]) || copy.structureFailed);
      } finally {
        setBusy(false);
      }
      return;
    }
    const kind = file ? sourceKindForFile(file) : "text";
    if (!kind || (!file && !text.trim())) return;
    setBusy(true);
    setError(null);
    try {
      const payload = file ? await blobBase64(file) : text.trim();
      await submit({ kind, payload, ...(file ? { name: file.name } : {}) });
    } catch (caught) {
      const code = errorCode(caught);
      setError((code && copy.readErrors[code]) || copy.structureFailed);
    } finally {
      setBusy(false);
    }
  };

  const ready = files.length > 0 || Boolean(text.trim());
  const total = files.length + (multiple && text.trim() ? 1 : 0);

  return (
    <div className="space-y-3">
      <div
        className="relative"
        onDragOver={(event) => {
          if (busy) return;
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          if (!busy) void take(Array.from(event.dataTransfer.files ?? []));
        }}
      >
        {file ? (
          <div className={cn("flex items-center justify-center rounded-lg border border-border bg-background px-4", minHeight)}>
            <span className="inline-flex items-center gap-2 rounded-full bg-secondary/60 py-1.5 pl-3 pr-1 text-sm text-foreground">
              <FileText size={14} strokeWidth={1.5} />
              <span className="max-w-[16rem] truncate">{file.name}</span>
              <IconAction label={copy.startRemoveFile} disabled={busy} onClick={() => setFiles([])}>
                <X size={12} strokeWidth={1.5} />
              </IconAction>
            </span>
          </div>
        ) : (
          <textarea
            className={cn(
              "block w-full resize-y rounded-lg border border-border bg-background px-4 py-3 text-[15px] leading-relaxed text-foreground",
              "placeholder:text-muted-foreground/70 focus:outline-none focus:ring-1 focus:ring-beige/40 transition-opacity duration-200",
              minHeight,
              busy && "opacity-50",
            )}
            value={text}
            readOnly={busy}
            placeholder={placeholder ?? copy.startPlaceholder}
            aria-label={placeholder ?? copy.startPlaceholder}
            onChange={(event) => setText(event.target.value)}
          />
        )}
        {multiple && files.length ? (
          <ul className="mt-2 flex flex-wrap gap-2" aria-label={copy.startAttach}>
            {files.map((one, index) => (
              <li key={`${one.name}:${index}`} className="inline-flex items-center gap-2 rounded-full bg-secondary/60 py-1 pl-3 pr-1 text-sm text-foreground">
                <FileText size={14} strokeWidth={1.5} aria-hidden />
                <span className="max-w-[14rem] truncate">{one.name}</span>
                <IconAction label={copy.startRemoveFile} disabled={busy} onClick={() => setFiles((current) => current.filter((_, at) => at !== index))}>
                  <X size={12} strokeWidth={1.5} />
                </IconAction>
              </li>
            ))}
          </ul>
        ) : null}
        {dragging ? (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center rounded-lg border border-dashed border-beige/60 bg-card/90 text-sm text-foreground">
            {copy.startDrop}
          </div>
        ) : null}
      </div>

      <div className="flex items-center gap-1">
        {!file && !busy ? (
          <VoiceComposer
            onText={(spoken) => setText((current) => appendDictation(current, spoken))}
            transcribe={playbooksApi.transcribe}
          />
        ) : null}
        {!busy && !(multiple && files.length >= MAX_FILES) ? (
          <IconAction label={copy.startAttach} onClick={() => input.current?.click()}>
            <Paperclip size={16} strokeWidth={1.5} />
          </IconAction>
        ) : null}
        <input
          ref={input}
          type="file"
          multiple={multiple}
          className="sr-only"
          tabIndex={-1}
          accept="application/pdf,.pdf,audio/*,.m4a,.mp3,.wav,.txt,.md,text/plain"
          onChange={(event) => {
            const picked = Array.from(event.target.files ?? []);
            event.target.value = "";
            void take(picked);
          }}
        />
        {busy ? (
          <p className="inline-flex items-center gap-2 pl-1 text-sm text-muted-foreground" role="status">
            <VocifySpinner size={12} />
            {multiple && total > 1 && manyReadingLabel ? manyReadingLabel.replace("{total}", String(total)) : (readingLabel ?? copy.structuring)}
          </p>
        ) : null}
        <span className="flex-1" />
        {onCancel && !busy ? (
          <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
            {t.product.cancelAction}
          </Button>
        ) : null}
        <Button type="button" size="sm" disabled={!ready || busy} onClick={() => void create()}>
          {copy.startCreate}
        </Button>
      </div>

      {multiple && manyHint && !busy ? <p className="text-[13px] text-muted-foreground">{manyHint}</p> : null}
      {error ? (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}
      {onTemplate && !busy ? (
        <button
          type="button"
          className={cn(THEME_TOKENS.typography.capsLabel, "underline-offset-4 hover:text-foreground hover:underline")}
          onClick={onTemplate}
        >
          {copy.startTemplate} →
        </button>
      ) : null}
    </div>
  );
}
