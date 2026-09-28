import { CaretDown } from "@phosphor-icons/react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { ProductTranslations } from "@/lib/product-catalog";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { hairline, type SectionOf } from "./shared";

function doneLine(row: SectionOf<"done">["rows"][number], copy: ProductTranslations) {
  const name = row.name || copy.today_unknown_contact;
  if (row.kind === "call") return copy.done_call.replace("{name}", name);
  if (row.kind === "followup") return copy.done_followup.replace("{name}", name);
  if (row.kind === "confirmation") return copy.done_confirmed.replace("{what}", name);
  return copy.done_signal.replace("{name}", name);
}

export function Done({ section, copy }: { section: SectionOf<"done">; copy: ProductTranslations }) {
  return (
    <Collapsible className="mt-7">
      <CollapsibleTrigger
        className={`group flex w-full items-center gap-1.5 border-t ${hairline} px-0.5 pt-3.5 ${THEME_TOKENS.typography.capsLabel} transition-colors hover:text-foreground`}
      >
        {copy.home_done} · <span className="tabular-nums">{section.count}</span>
        <CaretDown size={14} weight="light" className="ml-auto transition-transform group-data-[state=open]:rotate-180" />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ul className="mt-2">
          {section.rows.map((row, index) => (
            <li
              key={`${row.kind}:${row.at}:${row.name ?? ""}`}
              className={`grid grid-cols-[84px_1fr] items-baseline gap-3 px-0.5 py-2 ${index ? `border-t ${hairline}` : ""}`}
            >
              <span className={`tabular-nums ${THEME_TOKENS.typography.capsLabel}`}>{row.time}</span>
              <span className="text-[14px] leading-normal text-foreground">{doneLine(row, copy)}</span>
            </li>
          ))}
        </ul>
      </CollapsibleContent>
    </Collapsible>
  );
}
