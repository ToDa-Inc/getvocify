import { useEffect, useState } from "react";
import { getDesktopBridge, type RecordShortcutState } from "@/lib/desktop-host";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const MODIFIER_CODES = new Set(["MetaLeft", "MetaRight", "AltLeft", "AltRight", "ControlLeft", "ControlRight", "ShiftLeft", "ShiftRight"]);

/** The Mac app's global shortcut to start and stop recording. Only inside the app. */
export const RecordShortcutSettings = () => {
  const { t } = useLanguage();
  const shortcut = getDesktopBridge()?.shortcut;
  const [state, setState] = useState<RecordShortcutState | null>(null);
  const [listening, setListening] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    void shortcut?.get().then(setState);
  }, [shortcut]);

  useEffect(() => {
    if (!listening || !shortcut) return;
    const onKey = (event: KeyboardEvent) => {
      event.preventDefault();
      event.stopPropagation();
      if (event.code === "Escape") {
        setListening(false);
        return;
      }
      if (MODIFIER_CODES.has(event.code)) return;
      void shortcut
        .set({ code: event.code, meta: event.metaKey, alt: event.altKey, ctrl: event.ctrlKey, shift: event.shiftKey })
        .then((result) => {
          setState(result);
          if (result.ok) {
            setProblem(null);
            setListening(false);
          } else {
            setProblem(result.reason === "taken" ? t.product.recordShortcutTaken : t.product.recordShortcutInvalid);
          }
        });
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [listening, shortcut, t]);

  if (!shortcut || !state) return null;

  return (
    <div className="mt-6">
      <p className={`${THEME_TOKENS.typography.capsLabel} mb-2`}>{t.product.recordShortcutTitle}</p>
      <div className="flex items-center gap-2">
        <button
          type="button"
          aria-pressed={listening}
          onClick={() => {
            setProblem(null);
            setListening((on) => !on);
          }}
          className={`inline-flex h-9 min-w-20 items-center justify-center rounded-full border px-4 text-xs transition-colors ${
            listening
              ? "border-beige text-beige"
              : "border-border/40 bg-secondary/5 text-foreground hover:bg-secondary/10"
          }`}
        >
          {listening ? t.product.recordShortcutPress : state.label ?? t.product.recordShortcutOff}
        </button>
        {state.label && !listening ? (
          <button
            type="button"
            onClick={() => void shortcut.clear().then(setState)}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            {t.product.recordShortcutTurnOff}
          </button>
        ) : null}
      </div>
      <p className="mt-2 text-xs text-muted-foreground">{problem ?? t.product.recordShortcutHelper}</p>
    </div>
  );
};
