import { useState } from "react";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorCode, playbooksApi } from "@/features/playbooks/api";
import { RuleEditor } from "@/features/playbooks/components/RuleEditor";
import { linkButton } from "@/features/playbooks/styles";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useLanguage } from "@/lib/i18n";
import { typeKeyFromName, type AppliesTo, type CatalogType } from "@/lib/playbook-doc";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { LIVE_CHANNELS, ruleChannelsOf, type LiveChannel } from "@/lib/type-channels";

/** "+ Tipo de llamada": a catalog type, or the company's own with the rule that routes calls to it.
 * With types by channel (`channel` set, "+ Tipo de llamada" / "+ Tipo de reunión"): a catalog type that
 * fits the channel on screen, or the company's own with just a name. Either is created for that
 * channel only; a type that also serves the other one is switched on in the type's own settings. */
export function AddTypeMenu({
  catalog,
  stages,
  channel = null,
  byChannel = true,
  onAdded,
}: {
  catalog: CatalogType[];
  stages: { id: string; label: string }[];
  /** Types by channel: the channel the rail is on, which the new type belongs to. */
  channel?: LiveChannel | null;
  /** The company goes by channel (a type has channels, no rule); else a type is routed by a rule. */
  byChannel?: boolean;
  onAdded: (key: string, label: string, channels: LiveChannel[]) => void;
}) {
  const { t, language } = useLanguage();
  const copy = t.product.pb2;
  const lang = language === "EN" ? "en" : "es";
  const [open, setOpen] = useState(false);
  const [custom, setCustom] = useState(false);
  const [customName, setCustomName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const liveChannels = (channels: readonly string[]): LiveChannel[] =>
    LIVE_CHANNELS.filter((channel) => channels.includes(channel));

  const add = async (key: string, label: string, rule?: AppliesTo, channels?: LiveChannel[]) => {
    if (!key) return;
    // Without types by channel, a type in a channel is a rule: the catalog's (or "anyone, any contact") for
    // that channel alone, which the type's own "cambiar" refines later. Nothing to fill in to create it.
    if (channel && !byChannel) {
      const base = catalog.find((type) => type.key === key)?.applies_to;
      rule = { role: base?.role ?? "any", contact: base?.contact ?? "any", deal_stages: base?.deal_stages ?? [], channels: ruleChannelsOf(channel) as AppliesTo["channels"] };
      channels = undefined;
    }
    setBusy(true);
    setError(null);
    try {
      await playbooksApi.addType({
        type_key: key,
        name: label,
        ...(rule ? { applies_to: rule } : {}),
        ...(channels ? { channels } : {}),
      });
      setOpen(false);
      setCustom(false);
      setCustomName("");
      onAdded(key, label, channels ?? liveChannels(rule?.channels ?? catalog.find((type) => type.key === key)?.applies_to.channels ?? []));
    } catch (caught) {
      setError(errorCode(caught) === "rule_required" ? copy.ruleNone : copy.newTypeFailed);
    } finally {
      setBusy(false);
    }
  };

  const fitting = channel ? catalog.filter((type) => liveChannels(type.applies_to.channels).includes(channel)) : catalog;

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          setCustom(false);
          setError(null);
        }
      }}
    >
      <PopoverTrigger asChild>
        <button type="button" className={linkButton}>
          <Plus size={12} strokeWidth={1.5} />
          {channel ? copy.addTypeIn[channel] : copy.addType}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[22rem] max-w-[calc(100vw-2rem)] p-2">
        {!custom ? (
          <ul>
            {fitting.map((type) => (
              <li key={type.key}>
                <button
                  type="button"
                  disabled={busy}
                  className="flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left text-sm text-foreground hover:bg-secondary/60 disabled:opacity-50"
                  onClick={() => void add(type.key, type.label[lang], undefined, channel ? [channel] : undefined)}
                >
                  <span>{type.label[lang]}</span>
                  {channel ? null : <span className={THEME_TOKENS.typography.capsLabel}>{copy.ruleRoles[type.role]}</span>}
                </button>
              </li>
            ))}
            <li>
              <button
                type="button"
                className="w-full rounded-lg px-3 py-2 text-left text-sm text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
                onClick={() => setCustom(true)}
              >
                {copy.newTypeOther}…
              </button>
            </li>
          </ul>
        ) : (
          <div className="space-y-4 p-2">
            <input
              className="block w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/70 focus:outline-none focus:ring-1 focus:ring-beige/40"
              value={customName}
              placeholder={copy.newTypeName}
              aria-label={copy.newTypeName}
              autoFocus
              onChange={(event) => setCustomName(event.target.value)}
            />
            {channel ? (
              <div className="flex justify-end">
                <Button
                  type="button"
                  size="sm"
                  disabled={busy || !typeKeyFromName(customName)}
                  onClick={() => void add(typeKeyFromName(customName), customName.trim(), undefined, [channel])}
                >
                  {copy.newTypeCreate}
                </Button>
              </div>
            ) : (
              <RuleEditor
                value={null}
                stages={stages}
                saving={busy || !typeKeyFromName(customName)}
                saveLabel={copy.newTypeCreate}
                onSave={(rule) => void add(typeKeyFromName(customName), customName.trim(), rule)}
              />
            )}
          </div>
        )}
        {error ? <p className="px-3 pb-2 text-sm text-destructive">{error}</p> : null}
      </PopoverContent>
    </Popover>
  );
}
