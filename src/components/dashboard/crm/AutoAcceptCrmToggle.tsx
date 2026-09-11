import { Switch } from "@/components/ui/switch";
import { THEME_TOKENS } from "@/lib/theme/tokens";

type AutoAcceptCrmToggleProps = {
  checked: boolean;
  disabled?: boolean;
  onCheckedChange: (next: boolean) => void;
};

export const AutoAcceptCrmToggle = ({
  checked,
  disabled = false,
  onCheckedChange,
}: AutoAcceptCrmToggleProps) => {
  return (
    <div className="space-y-3">
      <h4 className={THEME_TOKENS.typography.capsLabel}>After each call</h4>
      <div
        className={
          checked
            ? "rounded-2xl border border-warning/30 bg-warning/5 p-4"
            : "rounded-2xl border border-border/20 bg-secondary/5 p-4"
        }
      >
        <div className="flex items-start gap-4">
          <div className="min-w-0 flex-1 space-y-2">
            <p className="text-[13px] text-foreground">Skip Approve and write to CRM</p>
            <p className="text-xs text-muted-foreground leading-relaxed">
              When a call or memo finishes processing, Vocify writes the note,
              tasks, and allowed fields. You review what was written afterwards
              — or correct it later. No one has to sit on Approve.
            </p>
            <ul className="text-xs text-muted-foreground leading-relaxed space-y-1 pt-1">
              <li>Applies to HubSpot recordings, Salesforce, the Vocify dialer, and memos already locked to a contact or deal.</li>
              <li>Does not change lead status, create deals, or write voicemail / no-answer stubs.</li>
            </ul>
            {checked ? (
              <p className="text-xs text-foreground pt-1">
                On: hang up and keep working. Open the memo later if something is wrong. Mistakes are yours.
              </p>
            ) : null}
          </div>
          <Switch
            aria-label="Skip Approve and write to CRM"
            className="shrink-0 mt-0.5 border-border/80 data-[state=unchecked]:bg-secondary data-[state=checked]:bg-beige data-[state=checked]:border-beige"
            checked={checked}
            disabled={disabled}
            onCheckedChange={onCheckedChange}
          />
        </div>
      </div>
    </div>
  );
};
