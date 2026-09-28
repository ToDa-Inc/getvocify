import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import type { Delta } from "./format";

interface KpiTileProps {
  label: string;
  value: string;
  hint: string;
  delta: Delta;
  comparison: string;
  testId?: string;
}

export function KpiTile({ label, value, hint, delta, comparison, testId }: KpiTileProps) {
  const Icon = delta?.direction === "up" ? ArrowUpRight : delta?.direction === "down" ? ArrowDownRight : Minus;
  return (
    <div
      className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-5 flex flex-col gap-2`}
      data-testid={testId}
    >
      <p className={THEME_TOKENS.typography.capsLabel}>{label}</p>
      <p className="text-[2rem] leading-none tracking-tight text-foreground tabular-nums">{value}</p>
      <p className="text-xs text-muted-foreground">
        {delta ? (
          <span className="inline-flex items-center gap-0.5 text-foreground">
            <Icon className="h-3.5 w-3.5" aria-hidden />
            {delta.text}
          </span>
        ) : (
          <span>No data to compare</span>
        )}
        {delta && <span> vs {comparison}</span>}
      </p>
      <p className="text-xs text-muted-foreground/80 leading-relaxed">{hint}</p>
    </div>
  );
}
