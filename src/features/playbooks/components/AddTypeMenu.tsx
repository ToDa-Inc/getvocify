import { useState } from "react";
import { Plus } from "lucide-react";
import { errorCode, playbooksApi } from "@/features/playbooks/api";
import { RuleEditor } from "@/features/playbooks/components/RuleEditor";
import { linkButton } from "@/features/playbooks/styles";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useLanguage } from "@/lib/i18n";
import { typeKeyFromName, type AppliesTo, type CatalogType } from "@/lib/playbook-doc";
import { THEME_TOKENS } from "@/lib/theme/tokens";

/** "+ Tipo de llamada": a catalog type, or the company's own with the rule that routes calls to it. */
export function AddTypeMenu({
  catalog,
  stages,
  onAdded,
}: {
  catalog: CatalogType[];
  stages: { id: string; label: string }[];
  onAdded: (key: string) => void;
}) {
  const { t, language } = useLanguage();
  const copy = t.product.pb2;
  const lang = language === "EN" ? "en" : "es";
  const [open, setOpen] = useState(false);
  const [custom, setCustom] = useState(false);
  const [customName, setCustomName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const add = async (key: string, label: string, rule?: AppliesTo) => {
    if (!key) return;
    setBusy(true);
    setError(null);
    try {
      await playbooksApi.addType({ type_key: key, name: label, ...(rule ? { applies_to: rule } : {}) });
      setOpen(false);
      setCustom(false);
      setCustomName("");
      onAdded(key);
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
          {copy.addType}
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
                  <span className={THEME_TOKENS.typography.capsLabel}>{copy.ruleRoles[type.role]}</span>
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
            <RuleEditor
              value={null}
              stages={stages}
              saving={busy || !typeKeyFromName(customName)}
              saveLabel={copy.newTypeCreate}
              onSave={(rule) => void add(typeKeyFromName(customName), customName.trim(), rule)}
            />
          </div>
        )}
        {error ? <p className="px-3 pb-2 text-sm text-destructive">{error}</p> : null}
      </PopoverContent>
    </Popover>
  );
}
