import { useLayoutEffect, useRef, useState } from "react";
import { ArrowUp, FileText, Paperclip, Sparkle, X } from "@phosphor-icons/react";
import VoiceComposer from "@/features/ask/components/VoiceComposer";
import { blobBase64, errorCode, playbooksApi, type FillSource } from "@/features/playbooks/api";
import { IconAction } from "@/components/ui/icon-action";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { useLanguage } from "@/lib/i18n";
import { appendDictation, sourceKindForFile } from "@/lib/playbook-doc";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

/**
 * "Dile a Vocify": one line where the manager says what to add, change or complete, by typing,
 * dictating or dropping a file. How a playbook or the company notes are edited after the first
 * import, instead of filling fields one by one. The owner decides what the request does.
 */
export function FillBox({
  placeholder,
  busy,
  submit,
}: {
  placeholder: string;
  /** A request (from here or from a "Completar" button) is being written. */
  busy: boolean;
  /** Throws on failure; an ApiError's detail.code becomes the message. */
  submit: (source: FillSource) => Promise<void>;
}) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const area = useRef<HTMLTextAreaElement>(null);
  const ready = !busy && (Boolean(file) || Boolean(text.trim()));

  // Grows with what is typed or dictated, up to max-h, then scrolls.
  useLayoutEffect(() => {
    const node = area.current;
    if (!node) return;
    node.style.height = "auto";
    node.style.height = `${node.scrollHeight}px`;
  }, [text, busy]);

  const take = async (picked: File | undefined) => {
    if (!picked) return;
    setError(null);
    const kind = sourceKindForFile(picked);
    if (!kind) {
      setError(copy.startUnsupported);
      return;
    }
    if (kind === "text") {
      const body = await picked.text();
      setText((current) => appendDictation(current, body));
      return;
    }
    setFile(picked);
  };

  const send = async () => {
    if (!ready) return;
    const kind = file ? sourceKindForFile(file) : "text";
    if (!kind) return;
    setError(null);
    try {
      const payload = file ? await blobBase64(file) : text.trim();
      await submit({ kind, payload, ...(file ? { name: file.name } : {}) });
      setText("");
      setFile(null);
    } catch (caught) {
      const code = errorCode(caught);
      setError((code && copy.readErrors[code]) || copy.fillFailed);
    }
  };

  return (
    <div className="space-y-1.5">
      <div
        className={cn(
          // Glass: it floats over the list (materials.css), the one surface on this page that does.
          "glass-panel relative flex items-center gap-1 rounded-[1.75rem] py-1.5 pl-4 pr-1.5 transition-shadow",
          "focus-within:ring-1 focus-within:ring-beige/40",
          dragging && "ring-1 ring-beige/60",
        )}
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
        onClick={() => area.current?.focus()}
      >
        <span className="flex h-8 shrink-0 items-center text-beige">
          {busy ? <VocifySpinner size={14} /> : <Sparkle size={16} weight="light" />}
        </span>
        <div className="flex min-h-8 min-w-0 flex-1 items-center">
          {file ? (
            <span className="inline-flex max-w-full items-center gap-1.5 rounded-full bg-secondary/70 py-0.5 pl-2.5 pr-0.5 text-sm text-foreground">
              <FileText size={13} weight="light" />
              <span className="truncate">{file.name}</span>
              <IconAction label={copy.startRemoveFile} disabled={busy} onClick={() => setFile(null)}>
                <X size={11} weight="light" />
              </IconAction>
            </span>
          ) : (
            <textarea
              ref={area}
              rows={1}
              value={busy ? "" : text}
              readOnly={busy}
              placeholder={busy ? copy.filling : placeholder}
              aria-label={placeholder}
              className="max-h-32 w-full resize-none bg-transparent py-1.5 text-sm leading-relaxed text-foreground placeholder:text-muted-foreground focus:outline-none"
              onChange={(event) => setText(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                  event.preventDefault();
                  void send();
                }
              }}
            />
          )}
        </div>
        {!busy && !file ? (
          <VoiceComposer onText={(spoken) => setText((current) => appendDictation(current, spoken))} transcribe={playbooksApi.transcribe} />
        ) : null}
        {!busy ? (
          <IconAction label={copy.startAttach} onClick={() => input.current?.click()}>
            <Paperclip size={16} weight="light" />
          </IconAction>
        ) : null}
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
        <button
          type="button"
          aria-label={copy.fillSend}
          disabled={!ready}
          onClick={(event) => {
            event.stopPropagation();
            void send();
          }}
          className={cn(
            "flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-colors",
            ready ? "bg-primary text-primary-foreground hover:bg-primary/90" : "bg-secondary text-muted-foreground",
          )}
        >
          <ArrowUp size={15} weight="bold" />
        </button>
      </div>
      {error ? (
        <p className={cn(THEME_TOKENS.typography.capsLabel, "px-3.5 text-destructive")} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
