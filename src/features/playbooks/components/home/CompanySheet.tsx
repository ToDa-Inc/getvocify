import { useEffect, useRef } from "react";
import { ProductOfferSettings } from "@/components/dashboard/settings/ProductOfferSettings";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { CompanyKnowledge } from "@/features/playbooks/components/CompanyKnowledge";
import { useLanguage } from "@/lib/i18n";
import type { CompanyOpens } from "@/lib/playbook-home";
import { THEME_TOKENS } from "@/lib/theme/tokens";

/**
 * "Vuestra empresa" as a window over the Playbook page: the product and offer text first (it used to live in Settings), then the
 * rest of what Vocify knows (who you sell to, value, cases, competitors, notes). Opened on the area that was clicked.
 */
export function CompanySheet({ open, onOpenChange, opens, canEdit, onSaved }: { open: boolean; onOpenChange: (open: boolean) => void; opens: CompanyOpens; canEdit: boolean; onSaved: () => void }) {
  const { t } = useLanguage();
  const c = t.product.pb2.home;
  const offer = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (open && opens === "offer") offer.current?.scrollIntoView({ block: "start" });
  }, [open, opens]);
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full space-y-8 overflow-y-auto sm:max-w-3xl">
        <SheetHeader className="space-y-2 text-left">
          <SheetTitle className={THEME_TOKENS.typography.panelTitle}>{c.companyTitle}</SheetTitle>
          <SheetDescription className="max-w-lg text-[15px] leading-relaxed text-muted-foreground">{c.companyWindowLead}</SheetDescription>
        </SheetHeader>
        <div ref={offer} className="scroll-mt-4">
          <ProductOfferSettings readOnly={!canEdit} />
        </div>
        <div className="border-t border-border/50 pt-8">
          <CompanyKnowledge key={String(opens)} canEdit={canEdit} onSaved={onSaved} initialTab={opens === "offer" ? undefined : opens} />
        </div>
      </SheetContent>
    </Sheet>
  );
}
