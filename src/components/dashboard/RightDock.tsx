import type { ReactNode } from "react";
import { X, type LucideIcon } from "lucide-react";
import { IconAction } from "@/components/ui/icon-action";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

/**
 * The dashboard's right dock: one panel at a time (Llamar, Hoy). On wide screens it sits beside the
 * page and the page makes room for it; on small ones it slides over the page. Its edge tabs are the
 * only way in besides a contact's own "Llamar".
 */
const PANEL =
  "fixed inset-y-0 right-0 z-40 flex w-[min(100vw,400px)] flex-col border-l border-border bg-card shadow-large transition-[transform,visibility] duration-200 ease-silk motion-reduce:transition-none xl:shadow-none";

export function DockPanel({
  open,
  label,
  children,
}: {
  open: boolean;
  label: string;
  children: ReactNode;
}) {
  return (
    <aside
      aria-label={label}
      aria-hidden={!open}
      className={cn(PANEL, open ? "translate-x-0" : "invisible pointer-events-none translate-x-full")}
    >
      {children}
    </aside>
  );
}

export function DockHeader({
  title,
  status,
  closeLabel,
  onClose,
  actions,
}: {
  title: string;
  status?: string;
  closeLabel: string;
  onClose: () => void;
  actions?: ReactNode;
}) {
  return (
    <header className="flex shrink-0 items-center gap-2 border-b border-border/60 px-4 py-3">
      <div className="min-w-0 flex-1">
        <h2 className={THEME_TOKENS.typography.groupTitle}>{title}</h2>
        {status ? <p className="mt-0.5 text-xs tabular-nums text-muted-foreground">{status}</p> : null}
      </div>
      {actions}
      <IconAction label={closeLabel} onClick={onClose}>
        <X aria-hidden className="h-4 w-4" strokeWidth={1.5} />
      </IconAction>
    </header>
  );
}

export function DockTabs({ children }: { children: ReactNode }) {
  return <div className="fixed right-0 top-1/2 z-30 flex -translate-y-1/2 flex-col gap-2">{children}</div>;
}

/** A slim vertical tab on the right edge. `live` lights it (a call in progress) and shows `liveText`. */
export function DockTab({
  label,
  icon: Icon,
  onClick,
  live = false,
  liveText,
}: {
  label: string;
  icon: LucideIcon;
  onClick: () => void;
  live?: boolean;
  liveText?: string;
}) {
  return (
    <button
      type="button"
      aria-label={live && liveText ? `${label}, ${liveText}` : label}
      onClick={onClick}
      className={cn(THEME_TOKENS.interaction.dockTab, live && THEME_TOKENS.interaction.dockTabLive)}
    >
      <Icon aria-hidden className="h-4 w-4" strokeWidth={1.5} />
      <span className="[writing-mode:vertical-rl] rotate-180 tabular-nums">{live && liveText ? liveText : label}</span>
    </button>
  );
}
