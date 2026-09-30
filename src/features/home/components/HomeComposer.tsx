import { forwardRef, useImperativeHandle, useRef, useState } from "react";
import Composer from "@/features/ask/components/Composer";
import { useAskSuggestions } from "@/features/ask/hooks/useAskSuggestions";
import { useLanguage } from "@/lib/i18n";

const MAX_SUGGESTIONS = 3;

export type HomeComposerHandle = {
  /** Where the composer sits now, so the thread's composer can glide in from here. */
  rect: () => DOMRect | null;
  /** Put a question in the field to edit or send, caret at its end (a team signal does this). */
  prefill: (text: string) => void;
};

/**
 * Inicio's question box: the Ask composer (Enter sends, Shift+Enter breaks the line, voice on the mic)
 * and up to three questions this account can really answer. A new account gets none.
 */
export const HomeComposer = forwardRef<HomeComposerHandle, { onSend: (text: string) => void; autoFocus: boolean }>(function HomeComposer(
  { onSend, autoFocus },
  ref,
) {
  const { t } = useLanguage();
  // The draft lives here, so typing re-renders the composer and not the feed and rail around it.
  const [value, setValue] = useState("");
  const send = (text: string) => {
    setValue("");
    onSend(text);
  };
  const copy = t.product as Record<string, string>;
  const box = useRef<HTMLDivElement>(null);
  const suggestions = useAskSuggestions()
    .map((id) => copy[`askSuggest_${id}`])
    .filter(Boolean)
    .slice(0, MAX_SUGGESTIONS);

  useImperativeHandle(ref, () => ({
    rect: () => box.current?.getBoundingClientRect() ?? null,
    prefill: (text) => {
      setValue(text);
      // After the text has rendered, so the caret lands at its end.
      requestAnimationFrame(() => {
        const field = box.current?.querySelector("textarea");
        if (!field) return;
        field.focus({ preventScroll: true });
        field.setSelectionRange(field.value.length, field.value.length);
      });
    },
  }));

  return (
    <div className="w-full">
      <div ref={box}>
        <Composer
          value={value}
          onChange={setValue}
          autoFocus={autoFocus}
          busy={false}
          onStop={() => undefined}
          onSend={() => {
            const text = value.trim();
            if (text) send(text);
          }}
        />
      </div>
      {suggestions.length > 0 ? (
        <ul className="mt-3 flex flex-wrap justify-center gap-2" aria-label={t.product.askTitle}>
          {suggestions.map((text) => (
            <li key={text}>
              <button
                type="button"
                onClick={() => send(text)}
                className="rounded-full border border-[hsl(var(--hairline))] bg-card/60 px-3.5 py-1.5 text-[13px] text-foreground/80 transition-colors duration-150 hover:bg-secondary/50 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none"
              >
                {text}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
});
