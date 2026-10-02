import type { ReactNode } from "react";
import { Ellipsis, Sparkles } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { useLanguage } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/**
 * The parts every playbook and company list is made of, so they all read the same way: one row
 * per item with a bold name and one plain line, a "Completar" that asks Vocify, and one "···"
 * for moving and deleting.
 */

/**
 * One item: a small mark on the left (number, quote), the name in bold, what sits on its right
 * (a type, a rate, the menu) and one line under it. A hairline separates items; inside an item
 * there is only space.
 */
export function DocRow({ lead, title, side, children }: { lead: ReactNode; title: ReactNode; side?: ReactNode; children?: ReactNode }) {
  return (
    <li className="group grid grid-cols-[1.75rem_minmax(0,1fr)_auto] items-start gap-x-3 border-t border-border/60 py-4 first:border-t-0">
      <span className="row-span-2 flex justify-center pt-0.5">{lead}</span>
      <div className="min-w-0">{title}</div>
      <div className="flex items-center gap-2 pt-0.5">{side}</div>
      {children ? <div className="col-span-2 col-start-2 min-w-0 pt-1">{children}</div> : null}
    </li>
  );
}

/** The number in front of a step. */
export function NumberMark({ n }: { n: number | string }) {
  return (
    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-secondary text-xs font-semibold tabular-nums text-foreground">
      {n}
    </span>
  );
}

/** The quote mark in front of what a prospect says. */
export function QuoteMark({ muted }: { muted?: boolean }) {
  return (
    <span aria-hidden className={cn("font-serif text-2xl leading-5", muted ? "text-muted-foreground/40" : "text-beige")}>
      “
    </span>
  );
}

/** A quiet tag on the right of an item ("Precio", "SDR"). */
export function TypeTag({ children }: { children: ReactNode }) {
  return <span className="whitespace-nowrap rounded-full bg-secondary px-2.5 py-0.5 text-[11.5px] text-muted-foreground">{children}</span>;
}

/** "✦ Completar con Vocify": asks Vocify to write what's missing; says so while it writes. */
export function CompleteButton({ label, pending, disabled, onClick }: { label: string; pending?: boolean; disabled?: boolean; onClick: () => void }) {
  const { t } = useLanguage();
  return (
    <button
      type="button"
      disabled={disabled || pending}
      aria-busy={pending}
      onClick={onClick}
      className="inline-flex items-center gap-1.5 rounded-full bg-beige/10 px-3 py-1 text-xs text-foreground transition-colors hover:bg-beige/20 disabled:cursor-default disabled:opacity-60 aria-busy:opacity-100"
    >
      {pending ? <VocifySpinner size={10} /> : <Sparkles size={12} strokeWidth={1.5} fill="currentColor" className="text-beige" />}
      {pending ? t.product.pb2.writing : label}
    </button>
  );
}

export type MenuAction = { label: string; onSelect: () => void; danger?: boolean };

/** One "···" per item, on the name's line: shown on hover or focus, always on touch. */
export function ItemMenu({ label, actions }: { label: string; actions: MenuAction[] }) {
  if (actions.length === 0) return null;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={label}
          className="-my-1 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-opacity hover:bg-secondary/60 hover:text-foreground md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100 data-[state=open]:opacity-100"
        >
          <Ellipsis size={16} strokeWidth={2.25} />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {actions.map((action) => (
          <DropdownMenuItem
            key={action.label}
            tone={action.danger ? "danger" : "default"}
            onSelect={action.onSelect}
          >
            {action.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
