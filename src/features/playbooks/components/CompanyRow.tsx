import { CaretRight } from "@phosphor-icons/react";
import { CompanyKnowledge } from "@/features/playbooks/components/CompanyKnowledge";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

/** "Vuestra empresa": shared by every call type, first in the list, with a one-line summary. */
export function CompanyRow({
  open,
  summary,
  canEdit,
  documentVersion,
  onToggleOpen,
  onSaved,
}: {
  open: boolean;
  summary: string | null;
  canEdit: boolean;
  documentVersion: number;
  onToggleOpen: () => void;
  onSaved: () => void;
}) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  return (
    <li className="border-t border-border/40 first:border-t-0">
      <button type="button" className="flex w-full items-center gap-3 py-4 text-left" aria-expanded={open} onClick={onToggleOpen}>
        <span className="text-[15px] text-foreground">{copy.companyTitle}</span>
        <span className="ml-auto flex shrink-0 items-center gap-3">
          <span className={cn(THEME_TOKENS.typography.capsLabel, "hidden truncate sm:inline")}>{summary ?? copy.statusMissing}</span>
          <CaretRight size={14} weight="light" className={cn("text-muted-foreground transition-transform duration-150", open && "rotate-90")} />
        </span>
      </button>
      {open ? (
        <div className={cn("pb-7 pt-1", THEME_TOKENS.motion.fadeIn)}>
          <CompanyKnowledge key={documentVersion} canEdit={canEdit} onSaved={onSaved} />
        </div>
      ) : null}
    </li>
  );
}
