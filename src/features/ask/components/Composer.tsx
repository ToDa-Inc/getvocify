import { useEffect, useRef } from "react";
import { PaperPlaneTilt, Stop } from "@phosphor-icons/react";
import { api } from "@/shared/lib/api-client";
import { IconAction } from "@/components/ui/icon-action";
import { useLanguage } from "@/lib/i18n";
import VoiceComposer from "./VoiceComposer";

const MAX_HEIGHT = 160;

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

export default function Composer({
  value,
  onChange,
  onSend,
  onStop,
  busy,
}: {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  onStop: () => void;
  busy: boolean;
}) {
  const { t } = useLanguage();
  const field = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = field.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`;
  }, [value]);

  const canSend = value.trim().length > 0 && !busy;
  return (
    <form
      className="border-t border-border/60 bg-background pb-[env(safe-area-inset-bottom)] pt-3"
      onSubmit={(event) => {
        event.preventDefault();
        if (canSend) onSend();
      }}
    >
      <div className="flex items-end gap-1 rounded-2xl border border-border/70 bg-card px-3 py-2 shadow-sm transition-colors focus-within:border-beige/40 focus-within:ring-2 focus-within:ring-beige/20">
        <textarea
          ref={field}
          rows={1}
          value={value}
          maxLength={4000}
          aria-label={t.product.askPlaceholder}
          placeholder={busy ? t.product.askPlaceholderWorking : t.product.askPlaceholder}
          className="block max-h-40 min-h-6 flex-1 resize-none bg-transparent py-1 text-[15px] leading-relaxed text-foreground outline-none placeholder:text-muted-foreground"
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
          <IconAction label={t.product.askStop} onClick={onStop}>
            <Stop size={16} weight="fill" />
          </IconAction>
        ) : (
          <IconAction label={t.product.askSend} disabled={!canSend} onClick={onSend}>
            <PaperPlaneTilt size={16} weight="light" />
          </IconAction>
        )}
      </div>
    </form>
  );
}
