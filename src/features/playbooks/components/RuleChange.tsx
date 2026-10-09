import { useState } from "react";
import { RuleEditor } from "@/features/playbooks/components/RuleEditor";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useLanguage } from "@/lib/i18n";
import type { AppliesTo } from "@/lib/playbook-doc";

/** "· cambiar" after the header sentence: which calls a playbook is used for, edited in place. */
export function RuleChange({
  rule,
  stages,
  crmOnly = false,
  onSave,
}: {
  rule: AppliesTo | null;
  stages: { id: string; label: string }[];
  /** Types by channel: only the CRM condition is edited here. */
  crmOnly?: boolean;
  onSave: (rule: AppliesTo) => Promise<void>;
}) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" className="text-foreground underline-offset-4 hover:underline">
          {rule ? copy.ruleChange : copy.ruleAdd}
        </button>
      </PopoverTrigger>
      {failed ? <span className="ml-2 text-destructive">{copy.ruleFailed}</span> : null}
      <PopoverContent align="start" className="w-[22rem] max-w-[calc(100vw-2rem)]">
        <RuleEditor
          value={rule}
          stages={stages}
          saving={saving}
          crmOnly={crmOnly}
          onSave={(next) => {
            setSaving(true);
            setFailed(false);
            void onSave(next)
              .then(() => setOpen(false))
              .catch(() => setFailed(true))
              .finally(() => setSaving(false));
          }}
        />
      </PopoverContent>
    </Popover>
  );
}
