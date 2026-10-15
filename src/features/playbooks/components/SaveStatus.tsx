import { useEffect, useState } from "react";
import { Check, CircleAlert } from "lucide-react";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { useLanguage } from "@/lib/i18n";
import type { SaveState } from "@/lib/playbook-doc";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

/** How long "Guardado" stays before it leaves: a confirmation, not a permanent label. */
const SAVED_MS = 2500;

/**
 * Autosave state in one quiet spot: a spinner while saving, a check that fades once saved,
 * and, only when something went wrong, the one action that fixes it (retry or reload).
 */
export function SaveStatus({
  state,
  dirty,
  onRetry,
  onReload,
}: {
  state: SaveState;
  dirty: boolean;
  onRetry: () => void;
  onReload: () => void;
}) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const [showSaved, setShowSaved] = useState(false);

  useEffect(() => {
    if (state !== "saved" || dirty) {
      setShowSaved(false);
      return;
    }
    setShowSaved(true);
    const timer = window.setTimeout(() => setShowSaved(false), SAVED_MS);
    return () => window.clearTimeout(timer);
  }, [state, dirty]);

  if (state === "error" || state === "stale") {
    return (
      <button
        type="button"
        className={cn(THEME_TOKENS.typography.capsLabel, "inline-flex items-center gap-1 text-warning underline-offset-4 hover:underline")}
        onClick={state === "stale" ? onReload : onRetry}
      >
        <CircleAlert size={14} strokeWidth={1.75} />
        {state === "stale" ? copy.stale : copy.saveError}
      </button>
    );
  }
  // One fixed-size slot, so a state coming and going never moves the actions next to it.
  const slot = "inline-flex h-5 w-5 items-center justify-center";
  if (state === "saving") {
    return (
      <span className={slot} role="status" title={copy.saving} aria-label={copy.saving}>
        <VocifySpinner size={12} />
      </span>
    );
  }
  return (
    <span
      className={cn(slot, "transition-opacity duration-500", showSaved ? "opacity-100" : "opacity-0")}
      role="status"
      title={copy.saved}
      aria-label={copy.saved}
      aria-hidden={!showSaved}
    >
      <Check size={14} strokeWidth={2.25} className="text-success" />
    </span>
  );
}
