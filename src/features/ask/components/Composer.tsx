import { useEffect, useRef, type ReactNode } from "react";
import { ArrowUp, Square } from "lucide-react";
import { api } from "@/shared/lib/api-client";
import { IconAction } from "@/components/ui/icon-action";
import { useLanguage } from "@/lib/i18n";
import VoiceComposer from "./VoiceComposer";

// One line of text is exactly as tall as the buttons beside it (36px): 22px line + 7px padding top and bottom.
const MAX_HEIGHT = 168;

async function transcribe(blob: Blob): Promise<string> {
  const dataUrl = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
  const comma = dataUrl.indexOf(",");
  const result = await api.post<{ text: string; memo_id: null }>("/ask/transcribe", {
    audio_base64: comma >= 0 ? dataUrl.slice(comma + 1) : dataUrl,
  });
  return result.text;
}

/** The composer's primary action: filled when there is something to send, like the Record button elsewhere. */
function PrimaryAction({ label, disabled, onClick, children }: { label: string; disabled?: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <IconAction label={label} tone="primary" disabled={disabled} onClick={onClick}>
      {children}
    </IconAction>
  );
}

export default function Composer({
  value,
  onChange,
  onSend,
  onStop,
  busy,
  autoFocus = false,
}: {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  onStop: () => void;
  busy: boolean;
  autoFocus?: boolean;
}) {
  const { t } = useLanguage();
  const field = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = field.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`;
    el.style.overflowY = el.scrollHeight > MAX_HEIGHT ? "auto" : "hidden";
  }, [value]);

  useEffect(() => {
    if (autoFocus) field.current?.focus({ preventScroll: true });
  }, [autoFocus]);

  const canSend = value.trim().length > 0 && !busy;
  return (
    <form
      className="pb-[env(safe-area-inset-bottom)]"
      onSubmit={(event) => {
        event.preventDefault();
        if (canSend) onSend();
      }}
    >
      <div className="ask-composer flex items-end gap-1 rounded-[22px] p-1.5">
        <textarea
          ref={field}
          rows={1}
          value={value}
          maxLength={4000}
          aria-label={t.product.askPlaceholder}
          placeholder={busy ? t.product.askPlaceholderWorking : t.product.askPlaceholder}
          className="block h-9 min-w-0 flex-1 resize-none overflow-hidden bg-transparent py-[7px] pl-3 pr-1 text-[15px] leading-[22px] text-foreground outline-none placeholder:text-muted-foreground/80"
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              if (canSend) onSend();
            }
          }}
        />
        <VoiceComposer onText={onChange} transcribe={transcribe} />
        {busy ? (
          <PrimaryAction label={t.product.askStop} onClick={onStop}>
            <Square size={13} strokeWidth={1.5} fill="currentColor" />
          </PrimaryAction>
        ) : (
          <PrimaryAction label={t.product.askSend} disabled={!canSend} onClick={onSend}>
            <ArrowUp size={16} strokeWidth={2.25} />
          </PrimaryAction>
        )}
      </div>
    </form>
  );
}
