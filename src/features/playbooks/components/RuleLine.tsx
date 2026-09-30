import { useState } from "react";
import { RuleEditor } from "@/features/playbooks/components/RuleEditor";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useLanguage } from "@/lib/i18n";
import { ruleSummary, type AppliesTo } from "@/lib/playbook-doc";
import { THEME_TOKENS } from "@/lib/theme/tokens";

/** "Se aplica a: Llamadas · SDR · cambiar": which calls a playbook is used for, editable in place. */
export function RuleLine({
  rule,
  stages,
  onSave,
}: {
  rule: AppliesTo | null;
  stages: { id: string; label: string }[];
  onSave: (rule: AppliesTo) => Promise<void>;
}) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);
  const summary = ruleSummary(rule, {
    roles: copy.ruleRoles,
    channels: copy.ruleChannels,
    contacts: copy.ruleContacts,
    stages: copy.ruleStages,
    join: copy.ruleJoin,
  });
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <p className={THEME_TOKENS.typography.capsLabel}>
        {summary ? `${copy.ruleLabel}: ${summary} · ` : `${copy.ruleNone} · `}
        <PopoverTrigger asChild>
          <button type="button" className="text-foreground underline-offset-4 hover:underline">
            {summary ? copy.ruleChange : copy.ruleAdd}
          </button>
        </PopoverTrigger>
        {failed ? <span className="ml-2 text-destructive">{copy.ruleFailed}</span> : null}
      </p>
      <PopoverContent align="start" className="w-[22rem] max-w-[calc(100vw-2rem)]">
        <RuleEditor
          value={rule}
          stages={stages}
          saving={saving}
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
