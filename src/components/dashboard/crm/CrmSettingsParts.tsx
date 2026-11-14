import { useEffect, useRef, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlignLeft, Briefcase, Building2, Check, MessageSquareText, UserRound } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/features/auth";
import { CALL_TARGETS, crmApi, crmKeys, SESSION_QUERY_STALE_MS, type CallNoteSettings, type CallTarget, type CRMConfiguration } from "@/lib/api/crm";
import { useLanguage } from "@/lib/i18n";
import { productText } from "@/lib/product-catalog";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SettingsRow } from "@/components/ui/settings-card";
import { Switch } from "@/components/ui/switch";
import { Toggle } from "@/components/ui/toggle";
import { VocifySpinner } from "@/components/ui/vocify-loader";

/**
 * Pieces shared by the HubSpot and Pipedrive settings, laid out in the order a call happens:
 * After a call (review or not), What Vocify creates, What Vocify writes. Every control saves on its own.
 */

export type SaveState = "idle" | "saving" | "saved" | "error";

/** Saves the draft a moment after the last change, and once more on leaving the page if one is pending. */
export function useAutosave<T>(draft: T | null, save: (value: T) => Promise<void>, delay = 600): SaveState {
  const [state, setState] = useState<SaveState>("idle");
  const saveRef = useRef(save);
  saveRef.current = save;
  const pending = useRef<T | null>(null);

  useEffect(() => {
    if (draft == null) return;
    pending.current = draft;
    setState("saving");
    const timer = setTimeout(async () => {
      pending.current = null;
      try {
        await saveRef.current(draft);
        setState("saved");
      } catch {
        setState("error");
      }
    }, delay);
    return () => clearTimeout(timer);
  }, [draft, delay]);

  useEffect(
    () => () => {
      if (pending.current != null) void saveRef.current(pending.current).catch(() => undefined);
    },
    [],
  );

  return state;
}

export const SaveStatus = ({ state }: { state: SaveState }) => {
  if (state === "saving")
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
        <VocifySpinner size={10} /> Saving
      </span>
    );
  if (state === "saved")
    return (
      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
        <Check className="h-3 w-3" /> Saved
      </span>
    );
  if (state === "error") return <span className="text-xs text-destructive">Not saved</span>;
  return null;
};

/** Summary and Transcript in the call note: one company-wide choice for every connected CRM. */
export const CallNoteRows = ({ disabled }: { disabled?: boolean }) => {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: crmKeys.noteSettings(),
    queryFn: () => crmApi.getNoteSettings(),
    staleTime: SESSION_QUERY_STALE_MS,
  });
  const mutation = useMutation({
    mutationFn: (next: CallNoteSettings) => crmApi.saveNoteSettings(next),
    onMutate: (next) => {
      const before = queryClient.getQueryData<CallNoteSettings>(crmKeys.noteSettings());
      queryClient.setQueryData(crmKeys.noteSettings(), next);
      return { before };
    },
    onSuccess: (saved) => queryClient.setQueryData(crmKeys.noteSettings(), saved),
    onError: (_e, _next, ctx) => {
      if (ctx?.before) queryClient.setQueryData(crmKeys.noteSettings(), ctx.before);
      toast.error("Could not save the call note setting");
    },
  });
  const note = data ?? { summary: true, transcript: true };
  const set = (patch: Partial<CallNoteSettings>) => mutation.mutate({ ...note, ...patch });
  const off = !note.summary && !note.transcript;
  return (
    <>
      <SettingsRow
        icon={AlignLeft}
        title="Call summary"
        description={off ? "No call note is written. Fields and tasks still are." : "What was said and agreed, as a note on the record"}
      >
        <Switch
          aria-label="Summary in the call note"
          checked={note.summary}
          disabled={disabled || !data}
          onCheckedChange={(on) => set({ summary: on })}
        />
      </SettingsRow>
      <SettingsRow icon={MessageSquareText} title="Transcript" description="The whole conversation, in the same note">
        <Switch
          aria-label="Transcript in the call note"
          checked={note.transcript}
          disabled={disabled || !data}
          onCheckedChange={(on) => set({ transcript: on })}
        />
      </SettingsRow>
    </>
  );
};

/** "Review before it goes to the CRM": the auto-write setting, said the right way round. */
export const ReviewRow = ({
  crmName,
  autoWrite,
  disabled,
  onAutoWriteChange,
}: {
  crmName: string;
  autoWrite: boolean;
  disabled?: boolean;
  onAutoWriteChange: (next: boolean) => void;
}) => (
  <SettingsRow
    title={`Review before it goes to ${crmName}`}
    description={
      autoWrite
        ? `Off: Vocify writes to ${crmName} as soon as the call is processed. Fix anything later from the call.`
        : "The rep checks the note, fields and deal, then approves."
    }
  >
    <Switch
      aria-label={`Review before it goes to ${crmName}`}
      checked={!autoWrite}
      disabled={disabled}
      onCheckedChange={(review) => onAutoWriteChange(!review)}
    />
  </SettingsRow>
);

/**
 * Where a call is saved: its note, call activity and tasks go on the chosen records it has. Any of the three, never
 * none (the last one can't be switched off). Without the deal, calls neither update nor create deals.
 */
const TARGET_ICONS: Record<CallTarget, LucideIcon> = { deal: Briefcase, company: Building2, contact: UserRound };

export const CallTargetsRow = ({
  labels,
  value,
  disabled,
  onChange,
}: {
  labels: Record<CallTarget, string>;
  value: CRMConfiguration["call_targets"];
  disabled?: boolean;
  onChange: (next: CallTarget[]) => void;
}) => {
  const on = value?.length ? value : CALL_TARGETS;
  return (
    <SettingsRow
      title="Save the call on"
      description={on.includes("deal") ? "Note, call and tasks" : `Note, call and tasks. ${labels.deal}s are left as they are.`}
      below={
        <div className="flex flex-wrap gap-2">
          {CALL_TARGETS.map((target) => {
            const pressed = on.includes(target);
            const Icon = pressed ? Check : TARGET_ICONS[target];
            return (
              <Toggle
                key={target}
                variant="chip"
                size="sm"
                className="gap-1.5"
                pressed={pressed}
                disabled={disabled}
                aria-label={`Save the call on the ${labels[target].toLowerCase()}`}
                title={pressed && on.length === 1 ? "The call needs somewhere to go" : undefined}
                onPressedChange={(next) => {
                  // The last one stays on (looks on, simply doesn't switch off).
                  if (!next && on.length === 1) return;
                  onChange(CALL_TARGETS.filter((t) => (t === target ? next : on.includes(t))));
                }}
              >
                <Icon className="h-3.5 w-3.5" strokeWidth={1.5} />
                {labels[target]}
              </Toggle>
            );
          })}
        </div>
      }
    />
  );
};

type DealRule = NonNullable<CRMConfiguration["deal_creation_rule"]>;
const WHEN_RULES: DealRule[] = ["always", "meeting_booked", "follow_up_or_meeting"];

/** The deal rule only takes effect for companies on the after-call flow. */
export const useDealRuleEnabled = () => {
  const { user } = useAuth();
  return Boolean(user?.company?.features?.includes("AFTER_CALL_FLOW_ENABLED"));
};

/** Deals in "What Vocify creates": a switch (with the rule) and, while on, where new deals go. */
export const DealsRow = ({
  icon,
  rule,
  disabled,
  notOnDeals = false,
  onRuleChange,
  children,
}: {
  icon: LucideIcon;
  rule: CRMConfiguration["deal_creation_rule"];
  disabled?: boolean;
  /** "Save the call on" leaves deals out: calls neither update nor create one, whatever this says. */
  notOnDeals?: boolean;
  onRuleChange: (rule: DealRule) => void;
  children: ReactNode;
}) => {
  const { t } = useLanguage();
  // The switch is for every company; "When" (by the call's outcome) needs the after-call flow.
  const ruleEnabled = useDealRuleEnabled();
  const current: DealRule = rule ?? "always";
  const on = current !== "never" && !notOnDeals;
  return (
    <SettingsRow
      icon={icon}
      title="Deals"
      description={
        notOnDeals
          ? "Off while calls aren't saved on deals"
          : on
            ? "When the contact has none. A deal that already exists is always updated."
            : "Never: calls land on the contact. Existing deals are still updated."
      }
      below={
        on ? (
          <div className="space-y-3">
            {ruleEnabled ? (
              <label className="block space-y-1.5">
                <span className="block text-[13px] text-foreground">When</span>
                <Select value={current} disabled={disabled} onValueChange={(next) => onRuleChange(next as DealRule)}>
                  <SelectTrigger className="w-full" aria-label="When Vocify creates a deal">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {WHEN_RULES.map((r) => (
                      <SelectItem key={r} value={r}>
                        {productText(`dealCreationRule_${r}`, t.product)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </label>
            ) : null}
            {children}
          </div>
        ) : null
      }
    >
      <Switch
        aria-label="Create deals"
        checked={on}
        disabled={disabled || notOnDeals}
        onCheckedChange={(next) => onRuleChange(next ? "always" : "never")}
      />
    </SettingsRow>
  );
};

/** One object's fields in "What Vocify writes": how many, which, and Edit to open the picker under it. */
export const FieldsRow = ({
  icon,
  label,
  names,
  open,
  readOnly,
  onToggle,
  children,
}: {
  icon: LucideIcon;
  label: string;
  names: string[];
  open: boolean;
  readOnly?: boolean;
  onToggle: () => void;
  children: ReactNode;
}) => {
  const preview = names.slice(0, 3).join(", ");
  const more = names.length > 3 ? ` +${names.length - 3}` : "";
  return (
    <SettingsRow
      icon={icon}
      title={`${label} fields`}
      description={names.length ? `${preview}${more}` : "None: nothing is filled from the call"}
      below={open ? children : null}
    >
      <Button
        size="sm"
        variant={open ? "secondary" : "outline"}
        className="h-8 rounded-full px-3 text-xs"
        onClick={onToggle}
      >
        {open ? "Done" : readOnly ? "View" : "Edit"}
      </Button>
    </SettingsRow>
  );
};
