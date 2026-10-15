import * as React from "react";
import { ChevronRight, type LucideIcon } from "lucide-react";

import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

/**
 * Settings pattern (Granola's Preferences): a small grey label above a rounded card whose rows are
 * split by a dashed hairline. A row is [icon tile] title + one-line description + a control on the right.
 */
export function SettingsSection({
  id,
  label,
  action,
  className,
  children,
}: {
  /** An anchor, for a link straight to this section. */
  id?: string;
  label?: React.ReactNode;
  /** A quiet action on the right of the label (e.g. "Reset"). */
  action?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className={cn("scroll-mt-6 space-y-2.5", className)}>
      {label || action ? (
        <div className="flex items-baseline justify-between gap-4 px-1">
          <h2 className={THEME_TOKENS.typography.capsLabel}>{label}</h2>
          {action}
        </div>
      ) : null}
      <div
        className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} divide-y divide-dashed divide-border/60 px-5 md:px-6`}
      >
        {children}
      </div>
    </section>
  );
}

type SettingsRowProps = {
  /** Where rows are different features, an icon tile; in forms and lists of the same kind, none. */
  icon?: LucideIcon;
  /** An image (a brand logo) instead of an icon. */
  logo?: string;
  title: React.ReactNode;
  description?: React.ReactNode;
  /** The control: Switch, Select, Segmented, Button. Not for rows that navigate (use `onClick`). */
  children?: React.ReactNode;
  /** A row with a chevron navigates: its `value` (e.g. "Connected") then `›`, and the whole row is the target. */
  onClick?: () => void;
  value?: React.ReactNode;
  /** Free content under the row (an inline detail, a status line). */
  below?: React.ReactNode;
  className?: string;
};

export function SettingsRow({ icon: Icon, logo, title, description, children, onClick, value, below, className }: SettingsRowProps) {
  const lead =
    logo ? (
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-secondary/10 p-1.5">
        <img src={logo} alt="" className="h-full w-full object-contain" />
      </span>
    ) : Icon ? (
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-secondary/10 text-muted-foreground">
        <Icon className="h-4 w-4" strokeWidth={1.5} />
      </span>
    ) : null;

  const text = (
    <span className="min-w-0 flex-1 text-left">
      <span className="block text-sm text-foreground">{title}</span>
      {description ? <span className="mt-0.5 block text-xs text-muted-foreground">{description}</span> : null}
    </span>
  );

  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className={cn("flex w-full items-center gap-4 py-4 text-left", THEME_TOKENS.interaction.rowHover, className)}
      >
        {lead}
        {text}
        {value ? <span className="shrink-0 text-xs text-muted-foreground">{value}</span> : null}
        <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.5} />
      </button>
    );
  }

  return (
    <div className={cn("py-4", className)}>
      <div className="flex items-center gap-4">
        {lead}
        {text}
        {children ? <div className="flex shrink-0 items-center gap-2">{children}</div> : null}
      </div>
      {below ? <div className={cn("mt-3", lead && "pl-[52px]")}>{below}</div> : null}
    </div>
  );
}
