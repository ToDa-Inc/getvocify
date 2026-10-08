import { Upload } from "lucide-react";
import { AddTypeMenu } from "@/features/playbooks/components/AddTypeMenu";
import { CompanyIcon, callTypeIcon } from "@/features/playbooks/icons";
import { COMPANY_ROW } from "@/features/playbooks/keys";
import { PUBLISH_TONE, linkButton } from "@/features/playbooks/styles";
import { useLanguage } from "@/lib/i18n";
import type { CatalogType, PublishState } from "@/lib/playbook-doc";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import type { LiveChannel } from "@/lib/type-channels";
import { cn } from "@/lib/utils";

/** `role` is the label shown next to the name ("SDR"), or null. */
export type NavItem = { key: string; label: string; state: PublishState; role: string | null };
/** Types by channel: the entries under "Llamadas" and under "Reuniones" (a type of both is in both). */
export type NavGroup = { label: string; items: NavItem[] };

/**
 * The left rail of "Vuestro proceso": "Vuestra empresa" and one entry per call type, each with
 * its icon and its state in one word, and the two ways to add (a document, a call type). On a
 * phone the same entries scroll sideways above the content.
 */
export function ProcessNav({
  items,
  selected,
  companyFilled,
  canEdit,
  onSelect,
  onImport,
  addable,
  stages,
  showAddType,
  groups = null,
  onTypeAdded,
}: {
  items: NavItem[];
  selected: string;
  companyFilled: boolean;
  canEdit: boolean;
  onSelect: (key: string) => void;
  onImport: () => void;
  addable: CatalogType[];
  stages: { id: string; label: string }[];
  showAddType: boolean;
  groups?: NavGroup[] | null;
  onTypeAdded: (key: string, label: string, channels: LiveChannel[]) => void;
}) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const word: Record<PublishState, string> = {
    live: copy.statusLive,
    changes: copy.statusChangesShort,
    unpublished: copy.statusUnpublished,
    paused: copy.statusPaused,
    empty: copy.statusMissing,
  };

  // The role is in the header of what is open; here it would only cut the name.
  const entry = (key: string, label: string, Icon: typeof CompanyIcon, state: PublishState | null, role?: string | null, group = "") => {
    const active = selected === key;
    return (
      <li key={`${group}:${key}`} className="shrink-0 md:shrink">
        <button
          type="button"
          aria-current={active ? "page" : undefined}
          onClick={() => onSelect(key)}
          className={cn(
            "flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left text-sm transition-colors",
            // The selected entry is a glass pill, like the app's own nav.
            active ? "glass-nav font-semibold text-foreground" : "border border-transparent text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
          )}
        >
          <Icon size={16} strokeWidth={active ? 1.75 : 1.5} className="shrink-0" />
          <span className="min-w-0 flex-1 truncate" title={role ? `${label} · ${role}` : label}>
            {label}
          </span>
          {state ? <span className={cn("shrink-0 text-[11px] font-normal", PUBLISH_TONE[state])}>{word[state]}</span> : null}
        </button>
      </li>
    );
  };

  return (
    <nav aria-label={copy.sectionTitle} className="md:w-60 md:shrink-0 md:border-r md:border-border/50 md:pr-3">
      <ul className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-1 [scrollbar-width:none] md:mx-0 md:flex-col md:overflow-visible md:px-0">
        {entry(COMPANY_ROW, copy.companyTitle, CompanyIcon, companyFilled ? null : "empty")}
        <li aria-hidden className="hidden md:block">
          <div className="mx-2.5 my-1.5 h-px bg-border/50" />
        </li>
        {groups
          ? groups.map((group) => (
              <li key={group.label} className="shrink-0 md:shrink">
                <p className={cn(THEME_TOKENS.typography.capsLabel, "px-3 pb-1 pt-2")}>{group.label}</p>
                <ul className="flex gap-1 md:flex-col">
                  {group.items.length ? (
                    group.items.map((item) => entry(item.key, item.label, callTypeIcon(item.key), item.state, null, group.label))
                  ) : (
                    <li className="px-3 py-1.5 text-[13px] text-muted-foreground">{copy.groupEmpty}</li>
                  )}
                </ul>
              </li>
            ))
          : items.map((item) => entry(item.key, item.label, callTypeIcon(item.key), item.state, item.role))}
      </ul>
      {canEdit ? (
        <div className="mt-2 flex flex-wrap gap-1 md:flex-col md:items-start">
          {showAddType ? <AddTypeMenu catalog={addable} stages={stages} byChannel={Boolean(groups)} onAdded={onTypeAdded} /> : null}
          <button type="button" className={cn(linkButton, "whitespace-nowrap")} onClick={onImport}>
            <Upload size={12} strokeWidth={1.5} />
            {copy.importDoc}
          </button>
        </div>
      ) : null}
    </nav>
  );
}
