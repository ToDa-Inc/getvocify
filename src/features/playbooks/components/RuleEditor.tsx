import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import { useLanguage } from "@/lib/i18n";
import { blankRule, type AppliesTo, type Channel, type ContactRule, type SalesRoleKey } from "@/lib/playbook-doc";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

const ROLES: SalesRoleKey[] = ["sdr", "ae", "any"];
const CHANNELS: Channel[] = ["call", "meeting", "visit"];
const CONTACTS: ContactRule[] = ["any", "new", "contacted", "inbound"];

/** "When does this playbook apply": who, channel, contact and, with a CRM, the deal stage. With
 * `crmOnly` (types by channel) only the CRM condition: the channels are set on the type itself and
 * there is no role. */
export function RuleEditor({
  value,
  stages,
  saving,
  saveLabel,
  crmOnly = false,
  onSave,
}: {
  value: AppliesTo | null;
  stages: { id: string; label: string }[];
  saving?: boolean;
  saveLabel?: string;
  crmOnly?: boolean;
  onSave: (rule: AppliesTo) => void;
}) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const [rule, setRule] = useState<AppliesTo>(value ?? blankRule());

  const toggle = <T,>(list: T[], item: T) => (list.includes(item) ? list.filter((x) => x !== item) : [...list, item]);

  const group = (label: string, body: React.ReactNode) => (
    <div className="space-y-1.5">
      <p className={THEME_TOKENS.typography.capsLabel}>{label}</p>
      <div className="flex flex-wrap gap-1">{body}</div>
    </div>
  );

  return (
    <div className="space-y-4">
      {crmOnly ? null : (
      <>
      <div className="space-y-1.5">
        <p className={THEME_TOKENS.typography.capsLabel}>{copy.ruleWho}</p>
        <Segmented
          value={rule.role}
          onValueChange={(role) => setRule({ ...rule, role: role as SalesRoleKey })}
          options={ROLES.map((role) => ({ value: role, label: copy.ruleRoles[role] }))}
          aria-label={copy.ruleWho}
        />
      </div>

      <div className="space-y-1.5">
        <p className={THEME_TOKENS.typography.capsLabel}>{copy.ruleChannel}</p>
        <div className="flex flex-wrap gap-1">
          {CHANNELS.map((channel) => (
            <button
              key={channel}
              type="button"
              aria-pressed={rule.channels.includes(channel)}
              onClick={() => {
                const channels = toggle(rule.channels, channel);
                if (channels.length) setRule({ ...rule, channels });
              }}
              className={cn(
                "rounded-full px-3 py-1 text-[13px] transition-colors",
                rule.channels.includes(channel) ? "bg-secondary text-foreground" : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
              )}
            >
              {copy.ruleChannels[channel]}
            </button>
          ))}
        </div>
      </div>
      </>
      )}

      <div className="space-y-1.5">
        <p className={THEME_TOKENS.typography.capsLabel}>{copy.ruleContact}</p>
        <Segmented
          value={rule.contact}
          onValueChange={(contact) => setRule({ ...rule, contact: contact as ContactRule })}
          options={CONTACTS.map((contact) => ({ value: contact, label: copy.ruleContacts[contact] }))}
          aria-label={copy.ruleContact}
        />
      </div>

      {stages.length > 0
        ? (
            <div className="space-y-1.5">
              <p className={THEME_TOKENS.typography.capsLabel}>{copy.ruleStage}</p>
              <div className="flex flex-wrap gap-1">
                <button
                  type="button"
                  aria-pressed={rule.deal_stages.length === 0}
                  onClick={() => setRule({ ...rule, deal_stages: [] })}
                  className={cn(
                    "rounded-full px-3 py-1 text-[13px] transition-colors",
                    rule.deal_stages.length === 0 ? "bg-secondary text-foreground" : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
                  )}
                >
                  {copy.ruleAnyStage}
                </button>
                {stages.map((stage) => (
                  <button
                    key={stage.id}
                    type="button"
                    aria-pressed={rule.deal_stages.includes(stage.id)}
                    onClick={() => setRule({ ...rule, deal_stages: toggle(rule.deal_stages, stage.id) })}
                    className={cn(
                      "rounded-full px-3 py-1 text-[13px] transition-colors",
                      rule.deal_stages.includes(stage.id) ? "bg-secondary text-foreground" : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
                    )}
                  >
                    {stage.label}
                  </button>
                ))}
              </div>
            </div>
          )
        : null}
      <div className="flex justify-end">
        <Button type="button" size="sm" disabled={saving} onClick={() => onSave(crmOnly ? { ...rule, role: "any" } : rule)}>
          {saveLabel ?? copy.ruleSave}
        </Button>
      </div>
    </div>
  );
}
