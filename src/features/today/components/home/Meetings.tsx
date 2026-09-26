import { itemKey } from "@shared/ui/home.js";
import type { ProductTranslations } from "@/lib/product-catalog";
import { useLeaving } from "../../hooks/useHomeMotion";
import { cardSelected, paper, type SectionOf } from "./shared";

type Entry = SectionOf<"meetings">["items"][number];
const entryKey = (entry: Entry) => itemKey(entry.item);

export function Meetings({
  section,
  copy,
  selectedKey,
  onSelect,
}: {
  section: SectionOf<"meetings">;
  copy: ProductTranslations;
  selectedKey: string | null;
  onSelect: (key: string) => void;
}) {
  const rows = useLeaving(section.items, entryKey);
  return (
    <div className="space-y-2">
      {rows.map(({ entry: { item, time, past }, leaving }) => {
        const key = itemKey(item);
        const selected = key === selectedKey;
        return (
          <div
            key={key}
            role="button"
            tabIndex={0}
            aria-current={selected || undefined}
            onClick={() => onSelect(key)}
            onFocus={(event) => {
              if (event.target === event.currentTarget) onSelect(key);
            }}
            className={`flex cursor-pointer items-baseline gap-3.5 px-[18px] py-[13px] outline-none transition-[border-color,box-shadow,opacity] duration-150 ${paper} ${
              selected ? cardSelected : "hover:border-beige/25 focus-visible:border-beige/25"
            } ${leaving ? "opacity-0" : past ? "opacity-60" : ""}`}
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
        );
      })}
    </div>
  );
}
