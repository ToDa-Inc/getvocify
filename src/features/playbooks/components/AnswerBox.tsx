import { useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowUp, FileText, Paperclip, X } from "lucide-react";
import VoiceComposer from "@/features/ask/components/VoiceComposer";
import { blobBase64, playbooksApi } from "@/features/playbooks/api";
import type { SourceInput } from "@/features/playbooks/components/PlaybookStart";
import { IconAction } from "@/components/ui/icon-action";
import { appendDictation, sourceKindForFile } from "@/lib/playbook-doc";
import { cn } from "@/lib/utils";

const MIN_HEIGHT = 96;
const MAX_HEIGHT = 260;

export type AnswerBoxCopy = {
  placeholder: string;
  submit: string;
  attach: string;
  removeFile: string;
  unsupported: string;
  hint?: string;
};

/**
 * Where the Head of Sales answers: the Ask composer's look (Inicio), a field for typing, the mic for dictating and a
 * clip for a PDF or an audio note. Ctrl/⌘+Enter sends; plain Enter breaks the line because answers are long. It only
 * gathers the source: the caller decides what to do with it, and what to show while it works.
 */
export function AnswerBox({
  value,
  onChange,
  onSubmit,
  busy = false,
  copy,
  focusKey,
  allowFile = true,
  footer,
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (source: SourceInput) => void;
  busy?: boolean;
  copy: AnswerBoxCopy;
  /** The field takes focus when this changes (a new question appears). */
  focusKey?: string;
  allowFile?: boolean;
  /** Quiet controls to the left of the send button ("Lo respondo luego"). */
  footer?: ReactNode;
  className?: string;
}) {
  const field = useRef<HTMLTextAreaElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  const latest = useRef(value);
  latest.current = value;
  const [file, setFile] = useState<File | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    const el = field.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(Math.max(el.scrollHeight, MIN_HEIGHT), MAX_HEIGHT)}px`;
    el.style.overflowY = el.scrollHeight > MAX_HEIGHT ? "auto" : "hidden";
  }, [value, file]);

  useEffect(() => {
    field.current?.focus({ preventScroll: true });
  }, [focusKey]);

  const take = async (picked: File | undefined) => {
    if (!picked) return;
    setProblem(null);
    const kind = sourceKindForFile(picked);
    if (!kind) {
      setProblem(copy.unsupported);
      return;
    }
    if (kind === "text") {
      onChange(appendDictation(latest.current, await picked.text()));
      return;
    }
    setFile(picked);
  };

  const ready = !busy && (Boolean(file) || value.trim().length > 0);
  const send = async () => {
    if (!ready) return;
    if (file) {
      const kind = sourceKindForFile(file);
      if (kind) onSubmit({ kind, payload: await blobBase64(file), name: file.name });
      return;
    }
    onSubmit({ kind: "text", payload: value.trim() });
  };

  return (
    <div className={className}>
      <div className="ask-composer flex flex-col gap-1 rounded-[22px] p-2">
        {file ? (
          <div className="flex min-h-[96px] items-center justify-center">
            <span className="inline-flex items-center gap-2 rounded-full bg-secondary/60 py-1.5 pl-3 pr-1 text-sm text-foreground">
              <FileText size={14} strokeWidth={1.5} aria-hidden />
              <span className="max-w-[16rem] truncate">{file.name}</span>
              <IconAction label={copy.removeFile} disabled={busy} onClick={() => setFile(null)}>
                <X size={12} strokeWidth={1.5} />
              </IconAction>
            </span>
          </div>
        ) : (
          <textarea
            ref={field}
            rows={3}
            value={value}
            readOnly={busy}
            maxLength={20000}
            aria-label={copy.placeholder}
            placeholder={copy.placeholder}
            className={cn(
              "block w-full resize-none bg-transparent px-3 py-2 text-[15px] leading-[22px] text-foreground outline-none placeholder:text-muted-foreground/80 transition-opacity duration-200",
              busy && "opacity-60",
            )}
            style={{ minHeight: MIN_HEIGHT }}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && (event.metaKey || event.ctrlKey) && !event.nativeEvent.isComposing) {
                event.preventDefault();
                void send();
              }
            }}
            onDragOver={(event) => allowFile && event.preventDefault()}
            onDrop={(event) => {
              if (!allowFile) return;
              event.preventDefault();
              void take(event.dataTransfer.files?.[0]);
            }}
          />
        )}
        <div className="flex items-center gap-1 pl-1">
          {!file && !busy ? <VoiceComposer onText={(spoken) => onChange(appendDictation(latest.current, spoken))} transcribe={playbooksApi.transcribe} /> : null}
          {allowFile && !busy ? (
            <IconAction label={copy.attach} onClick={() => picker.current?.click()}>
              <Paperclip size={16} strokeWidth={1.5} />
            </IconAction>
          ) : null}
          <input
            ref={picker}
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
          {copy.hint ? <span className="hidden pr-1 text-xs text-muted-foreground md:inline">{copy.hint}</span> : null}
          {footer}
          <IconAction label={copy.submit} tone="primary" pending={busy} disabled={!ready} onClick={() => void send()}>
            <ArrowUp size={16} strokeWidth={2.25} />
          </IconAction>
        </div>
      </div>
      {problem ? (
        <p className="mt-2 px-3 text-sm text-destructive" role="alert">
          {problem}
        </p>
      ) : null}
    </div>
  );
}
