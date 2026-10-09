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
import { LIVE_CHANNELS, type LiveChannel } from "@/lib/type-channels";
import { cn } from "@/lib/utils";

/** "+ Tipo de llamada": a catalog type, or the company's own with the rule that routes calls to it.
 * With types by channel ("+ Tipo de interacción"): a catalog type, or the company's own with a name
 * and its channels, nothing else. */
export function AddTypeMenu({
  catalog,
  stages,
  byChannel = false,
  onAdded,
}: {
  catalog: CatalogType[];
  stages: { id: string; label: string }[];
  byChannel?: boolean;
  onAdded: (key: string, label: string, channels: LiveChannel[]) => void;
}) {
  const { t, language } = useLanguage();
  const copy = t.product.pb2;
  const lang = language === "EN" ? "en" : "es";
  const [open, setOpen] = useState(false);
  const [custom, setCustom] = useState(false);
  const [customName, setCustomName] = useState("");
  const [customChannels, setCustomChannels] = useState<LiveChannel[]>(["call"]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const liveChannels = (channels: readonly string[]): LiveChannel[] =>
    LIVE_CHANNELS.filter((channel) => channels.includes(channel));

  const add = async (key: string, label: string, rule?: AppliesTo, channels?: LiveChannel[]) => {
    if (!key) return;
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
          {byChannel ? copy.addInteractionType : copy.addType}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[22rem] max-w-[calc(100vw-2rem)] p-2">
        {!custom ? (
          <ul>
            {catalog.map((type) => (
              <li key={type.key}>
                <button
                  type="button"
                  disabled={busy}
                  className="flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left text-sm text-foreground hover:bg-secondary/60 disabled:opacity-50"
                  onClick={() => void add(type.key, type.label[lang])}
                >
                  <span>{type.label[lang]}</span>
                  <span className={THEME_TOKENS.typography.capsLabel}>
                    {byChannel
                      ? liveChannels(type.applies_to.channels).map((channel) => copy.ruleChannels[channel]).join(" · ")
                      : copy.ruleRoles[type.role]}
                  </span>
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
            {byChannel ? (
              <div className="flex items-center justify-between gap-3">
                <div className="flex gap-1" role="group" aria-label={copy.typeChannel}>
                  {LIVE_CHANNELS.map((channel) => {
                    const on = customChannels.includes(channel);
                    return (
                      <button
                        key={channel}
                        type="button"
                        aria-pressed={on}
                        disabled={on && customChannels.length === 1}
                        onClick={() =>
                          setCustomChannels(liveChannels(on ? customChannels.filter((item) => item !== channel) : [...customChannels, channel]))
                        }
                        className={cn(
                          "rounded-full px-3 py-1 text-[13px] transition-colors disabled:cursor-default",
                          on ? "bg-secondary text-foreground" : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
                        )}
                      >
                        {copy.ruleChannels[channel]}
                      </button>
                    );
                  })}
                </div>
                <Button
                  type="button"
                  size="sm"
                  disabled={busy || !typeKeyFromName(customName)}
                  onClick={() => void add(typeKeyFromName(customName), customName.trim(), undefined, customChannels)}
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
