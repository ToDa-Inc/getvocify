import type { ProductTranslations } from "@/lib/product-catalog";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { hairline, type SectionOf } from "./shared";

export function Upcoming({ section, copy }: { section: SectionOf<"upcoming">; copy: ProductTranslations }) {
  return (
    <div>
      {section.rows.map((row, index) => (
        <div
          key={`${row.memo_id}:${row.due_at}:${row.text}`}
          className={`grid grid-cols-[84px_1fr_auto] items-baseline gap-3 px-0.5 py-2 ${index ? `border-t ${hairline}` : ""}`}
        >
          <span className={THEME_TOKENS.typography.capsLabel}>{row.when}</span>
          <span className="text-[14px] leading-normal text-foreground">{row.text}</span>
          {row.inCrm ? <span className="v-chip whitespace-nowrap">{copy.home_in_crm}</span> : <span />}
        </div>
      ))}
    </div>
  );
}
