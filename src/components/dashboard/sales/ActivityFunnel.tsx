import { formatCount, formatPercent } from "./format";

interface Step {
  label: string;
  value: number;
}

/** Horizontal funnel: each bar is its share of the first step; the label shows step-to-step conversion. */
export function ActivityFunnel({ steps }: { steps: Step[] }) {
  const top = steps[0]?.value ?? 0;
  return (
    <ol className="space-y-3" aria-label="Activity funnel">
      {steps.map((step, index) => {
        const prev = index > 0 ? steps[index - 1].value : null;
        const conversion = prev ? step.value / prev : null;
        const width = top ? Math.max((step.value / top) * 100, step.value ? 2 : 0) : 0;
        return (
          <li key={step.label} className="grid grid-cols-[9rem_minmax(0,1fr)_4.5rem] items-center gap-3">
            <span className="text-[13px] text-muted-foreground truncate">{step.label}</span>
            <div className="h-7 rounded-md bg-secondary/40 overflow-hidden" aria-hidden>
              <div
                className="h-full rounded-r-[4px]"
                style={{ width: `${width}%`, backgroundColor: "hsl(var(--chart-activity))" }}
              />
            </div>
            <span className="text-right tabular-nums">
              <span className="text-sm text-foreground">{formatCount(step.value)}</span>
              {index > 0 && (
                <span className="block text-[11px] text-muted-foreground">
                  {conversion == null ? "—" : formatPercent(conversion)} of prev.
                </span>
              )}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
