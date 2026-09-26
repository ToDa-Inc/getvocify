import type { ProductTranslations } from "@/lib/product-catalog";
import { paper, type SectionOf } from "./shared";

export function Meetings({ section, copy }: { section: SectionOf<"meetings">; copy: ProductTranslations }) {
  return (
    <div className="space-y-2">
      {section.items.map(({ item, time, past }) => (
        <div
          key={item.id ?? item.dedupe_key ?? item.reason}
          className={`flex items-baseline gap-3.5 px-[18px] py-[13px] ${paper} ${past ? "opacity-60" : ""}`}
        >
          <p className="min-w-10 shrink-0 whitespace-nowrap text-[15px] leading-normal tabular-nums text-foreground">
            {time ?? copy.home_meeting_no_time}
          </p>
          <p className="min-w-0 truncate text-[15px] leading-normal text-foreground">
            {item.reason || item.contact_name || copy.today_unknown_contact}
            {item.company_name ? <span className="text-muted-foreground"> · {item.company_name}</span> : null}
          </p>
          {item.detail ? (
            <p className="ml-auto max-w-[45%] shrink-0 truncate text-right text-[13.5px] leading-normal text-muted-foreground">{item.detail}</p>
          ) : null}
        </div>
      ))}
    </div>
  );
}
