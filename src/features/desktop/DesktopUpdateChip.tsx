import { ArrowDownToLine } from "lucide-react";
import { useLanguage } from "@/lib/i18n";
import { useDesktopUpdates } from "./useDesktopUpdates";

/**
 * A downloaded build waiting for the rep: Vocify never restarts by itself to update, so the sidebar offers the restart
 * (the desktop app also says so once with a system notice). It waits while a recording or a note being saved holds it.
 */
export function DesktopUpdateChip() {
  const updates = useDesktopUpdates();
  const { language } = useLanguage();
  const status = updates?.status;
  if (!updates?.install || status?.state !== "ready") return null;
  const es = language === "ES";
  const label = updates.mustWait
    ? es ? "Se actualiza al acabar la llamada" : "Updates when the call ends"
    : es ? `${status.next} lista` : `${status.next} ready`;
  return (
    <div className="flex items-center gap-2 rounded-full border border-beige/25 bg-beige/10 py-1 pl-3 pr-1 text-xs font-medium text-foreground animate-in fade-in duration-200 motion-reduce:animate-none">
      <ArrowDownToLine className="h-3.5 w-3.5 shrink-0 text-beige" />
      {/* Short enough to fit whole: cut with "…" it read as something still loading (2026-11-20). */}
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {updates.mustWait ? null : (
        <button
          type="button"
          onClick={updates.install}
          className="shrink-0 rounded-full bg-foreground px-2.5 py-0.5 text-background transition-opacity duration-150 hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-beige/60"
        >
          {es ? "Reiniciar" : "Restart"}
        </button>
      )}
    </div>
  );
}
