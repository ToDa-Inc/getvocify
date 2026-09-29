import { useRef, useState } from "react";
import { FileText, Paperclip, X } from "@phosphor-icons/react";
import VoiceComposer from "@/features/ask/components/VoiceComposer";
import { blobBase64, errorCode, playbooksApi } from "@/features/playbooks/api";
import { Button } from "@/components/ui/button";
import { IconAction } from "@/components/ui/icon-action";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { useLanguage } from "@/lib/i18n";
import { appendDictation, sourceKindForFile, type StructureResult } from "@/lib/playbook-doc";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

/**
 * The one box a playbook starts from (plan §4.2): write, paste, dictate or drop a file, and
 * Vocify turns it into steps and answers. Whatever the source, it lands in the same document.
 */
export function PlaybookStart({
  motionKey,
  onResult,
  onTemplate,
  onCancel,
}: {
  motionKey: string;
  onResult: (result: StructureResult) => void;
  /** Omitted when rebuilding an existing playbook: the template is for a blank start. */
  onTemplate?: () => void;
  onCancel?: () => void;
}) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const take = async (picked: File | undefined) => {
    if (!picked) return;
    setError(null);
    const kind = sourceKindForFile(picked);
    if (!kind) {
      setError(copy.startUnsupported);
      return;
    }
    if (kind === "text") {
      // A text file is just text: show it, so it can be read and trimmed before creating.
      const body = await picked.text();
      setText((current) => appendDictation(current, body));
      return;
    }
    setFile(picked);
  };

  const create = async () => {
    const kind = file ? sourceKindForFile(file) : "text";
    if (!kind || (!file && !text.trim())) return;
    setBusy(true);
    setError(null);
    try {
      const payload = file ? await blobBase64(file) : text.trim();
      const result = await playbooksApi.structure(motionKey, kind, payload, file?.name);
      onResult(result);
    } catch (caught) {
      const code = errorCode(caught);
      setError((code && copy.readErrors[code]) || copy.structureFailed);
    } finally {
      setBusy(false);
    }
  };

  const ready = Boolean(file) || Boolean(text.trim());

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
          if (!busy) void take(event.dataTransfer.files?.[0]);
        }}
      >
        {file ? (
          <div className="flex min-h-[152px] items-center justify-center rounded-lg border border-border bg-background px-4">
            <span className="inline-flex items-center gap-2 rounded-full bg-secondary/60 py-1.5 pl-3 pr-1 text-sm text-foreground">
              <FileText size={14} weight="light" />
              <span className="max-w-[16rem] truncate">{file.name}</span>
              <IconAction label={copy.startRemoveFile} disabled={busy} onClick={() => setFile(null)}>
                <X size={12} weight="light" />
              </IconAction>
            </span>
          </div>
        ) : (
          <textarea
            className={cn(
              "block min-h-[152px] w-full resize-y rounded-lg border border-border bg-background px-4 py-3 text-[15px] leading-relaxed text-foreground",
              "placeholder:text-muted-foreground/70 focus:outline-none focus:ring-1 focus:ring-beige/40 transition-opacity",
              busy && "opacity-60",
            )}
            value={text}
            readOnly={busy}
            placeholder={copy.startPlaceholder}
            aria-label={copy.startPlaceholder}
            onChange={(event) => setText(event.target.value)}
          />
        )}
        {dragging ? (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center rounded-lg border border-dashed border-beige/60 bg-card/90 text-sm text-foreground">
            {copy.startDrop}
          </div>
        ) : null}
      </div>

      <div className="flex items-center gap-1">
        {!file ? (
          <VoiceComposer
            onText={(spoken) => setText((current) => appendDictation(current, spoken))}
            transcribe={playbooksApi.transcribe}
          />
        ) : null}
        <IconAction label={copy.startAttach} disabled={busy} onClick={() => input.current?.click()}>
          <Paperclip size={16} weight="light" />
        </IconAction>
        <input
          ref={input}
          type="file"
          className="sr-only"
          tabIndex={-1}
          accept="application/pdf,.pdf,audio/*,.m4a,.mp3,.wav,.txt,.md,text/plain"
          onChange={(event) => {
            const picked = event.target.files?.[0];
            event.target.value = "";
            void take(picked);
          }}
        />
        <span className="flex-1" />
        {onCancel ? (
          <Button type="button" variant="ghost" size="sm" disabled={busy} onClick={onCancel}>
            {t.product.cancelAction}
          </Button>
        ) : null}
        <Button type="button" size="sm" disabled={!ready || busy} onClick={() => void create()}>
          {copy.startCreate}
        </Button>
      </div>

      {busy ? (
        <p className="inline-flex items-center gap-2 text-sm text-muted-foreground" role="status">
          <VocifySpinner size={12} />
          {copy.structuring}
        </p>
      ) : null}
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
