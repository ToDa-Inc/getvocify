import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Checkbox } from "@/components/ui/checkbox";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { InlineTextarea } from "@/features/playbooks/components/InlineField";
import { RuleChange } from "@/features/playbooks/components/RuleChange";
import { useLanguage } from "@/lib/i18n";
import type { AppliesTo } from "@/lib/playbook-doc";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { channelsLabelKey, LIVE_CHANNELS, type LiveChannel } from "@/lib/type-channels";

const CHANNELS_TEXT = { call: "typeChannelsCall", meeting: "typeChannelsMeeting", both: "typeChannelsBoth" } as const;

/**
 * Types by channel: under a type's name, the three things that make Vocify detect it. Its channels
 * (a line of text; a manager ticks them in a popover, at least one), the one sentence that says how
 * to recognise it, and how it did in the last 30 days; the CRM condition is one link away. A type
 * reads as a document, never a form.
 */
export function TypeSetup({
  channels,
  recognize,
  stats,
  rule,
  stages,
  canEdit,
  onEdit,
  onSaveRule,
}: {
  channels: LiveChannel[];
  recognize: string | null;
  stats: { count: number; corrected: number } | null;
  rule: AppliesTo | null;
  stages: { id: string; label: string }[];
  canEdit: boolean;
  onEdit: (edit: { channels?: LiveChannel[]; recognize?: string }) => Promise<void>;
  onSaveRule: (rule: AppliesTo) => Promise<void>;
}) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const [sentence, setSentence] = useState(recognize ?? "");
  // Typed by the person and not saved yet: until then the field follows the stored sentence (Vocify's
  // draft lands a moment after the type is created).
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (!dirty) setSentence(recognize ?? "");
  }, [recognize, dirty]);

  const save = (edit: { channels?: LiveChannel[]; recognize?: string }) => {
    setSaving(true);
    void onEdit(edit)
      .catch(() => toast.error(copy.typeSaveFailed))
      .finally(() => setSaving(false));
  };

  const toggle = (channel: LiveChannel) => {
    const next = channels.includes(channel) ? channels.filter((item) => item !== channel) : [...channels, channel];
    if (next.length) save({ channels: LIVE_CHANNELS.filter((item) => next.includes(item)) });
  };

  const statsLine = stats?.count
    ? copy.typeStats.replace("{count}", String(stats.count)).replace("{corrected}", String(stats.corrected))
    : copy.typeStatsNone;

  const channelsText = copy[CHANNELS_TEXT[channelsLabelKey(channels)]];

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className={THEME_TOKENS.typography.capsLabel}>
          {canEdit ? (
            <Popover>
              <PopoverTrigger asChild>
                <button type="button" className="text-foreground underline-offset-4 hover:underline">
                  {channelsText}
                </button>
              </PopoverTrigger>
              <PopoverContent align="start" className="w-56">
                <p className="mb-2 text-[13px] text-muted-foreground">{copy.typeUsedIn}</p>
                <div className="space-y-2">
                  {LIVE_CHANNELS.map((channel) => {
                    const on = channels.includes(channel);
                    return (
                      <label key={channel} className="flex items-center gap-2 text-sm">
                        <Checkbox
                          checked={on}
                          disabled={saving || (on && channels.length === 1)}
                          onCheckedChange={() => toggle(channel)}
                        />
                        {copy.ruleChannels[channel]}
                      </label>
                    );
                  })}
                </div>
              </PopoverContent>
            </Popover>
          ) : (
            channelsText
          )}
          {" · "}
          {statsLine}
          {canEdit ? (
            <>
              {" · "}
              {copy.crmCondition}{" "}
              <RuleChange
                rule={{ ...(rule ?? { role: "any", contact: "any", deal_stages: [] }), channels }}
                stages={stages}
                crmOnly
                onSave={onSaveRule}
              />
            </>
          ) : null}
        </span>
      </div>
      {canEdit ? (
        <InlineTextarea
          value={sentence}
          maxLength={300}
          placeholder={copy.recognizePlaceholder}
          aria-label={copy.recognizeLabel}
          className="text-sm text-muted-foreground"
          onChange={(event) => {
            setSentence(event.target.value);
            setDirty(true);
          }}
          onBlur={() => {
            if (!dirty) return;
            if (sentence.trim() === (recognize ?? "").trim()) {
              setDirty(false);
              return;
            }
            // Stays as typed until saved; a failed save keeps the text so nothing is lost.
            setSaving(true);
            void onEdit({ recognize: sentence.trim() })
              .then(() => setDirty(false))
              .catch(() => toast.error(copy.typeSaveFailed))
              .finally(() => setSaving(false));
          }}
        />
      ) : recognize ? (
        <p className="text-sm text-muted-foreground">{recognize}</p>
      ) : null}
    </div>
  );
}
