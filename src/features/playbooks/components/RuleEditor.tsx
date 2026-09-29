import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useLanguage } from "@/lib/i18n";
import { blankRule, type AppliesTo, type Channel, type ContactRule, type SalesRoleKey } from "@/lib/playbook-doc";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

const ROLES: SalesRoleKey[] = ["sdr", "ae", "any"];
const CHANNELS: Channel[] = ["call", "meeting", "visit"];
const CONTACTS: ContactRule[] = ["any", "new", "contacted", "inbound"];

function Pill({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "rounded-full px-3 py-1 text-[13px] transition-colors",
        active ? "bg-secondary text-foreground" : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

/** "When does this playbook apply": who, channel, contact and, with a CRM, the deal stage. */
export function RuleEditor({
  value,
  stages,
  saving,
  saveLabel,
  onSave,
}: {
  value: AppliesTo | null;
  stages: { id: string; label: string }[];
  saving?: boolean;
  saveLabel?: string;
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
      {group(
        copy.ruleWho,
        ROLES.map((role) => (
          <Pill key={role} active={rule.role === role} onClick={() => setRule({ ...rule, role })}>
            {copy.ruleRoles[role]}
          </Pill>
        )),
      )}
      {group(
        copy.ruleChannel,
        CHANNELS.map((channel) => (
          <Pill
            key={channel}
            active={rule.channels.includes(channel)}
            onClick={() => {
              const channels = toggle(rule.channels, channel);
              if (channels.length) setRule({ ...rule, channels });
            }}
          >
            {copy.ruleChannels[channel]}
          </Pill>
        )),
      )}
      {group(
        copy.ruleContact,
        CONTACTS.map((contact) => (
          <Pill key={contact} active={rule.contact === contact} onClick={() => setRule({ ...rule, contact })}>
            {copy.ruleContacts[contact]}
          </Pill>
        )),
      )}
      {stages.length > 0
        ? group(copy.ruleStage, [
            <Pill key="any" active={rule.deal_stages.length === 0} onClick={() => setRule({ ...rule, deal_stages: [] })}>
              {copy.ruleAnyStage}
            </Pill>,
            ...stages.map((stage) => (
              <Pill
                key={stage.id}
                active={rule.deal_stages.includes(stage.id)}
                onClick={() => setRule({ ...rule, deal_stages: toggle(rule.deal_stages, stage.id) })}
              >
                {stage.label}
              </Pill>
            )),
          ])
        : null}
      <div className="flex justify-end">
        <Button type="button" size="sm" disabled={saving} onClick={() => onSave(rule)}>
          {saveLabel ?? copy.ruleSave}
        </Button>
      </div>
    </div>
  );
}
