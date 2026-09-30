import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Plus, Trash } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { IconAction } from "@/components/ui/icon-action";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { errorCode, playbooksApi } from "@/features/playbooks/api";
import { linkButton } from "@/features/playbooks/styles";
import { InlineTextarea } from "@/features/playbooks/components/InlineField";
import { useLanguage } from "@/lib/i18n";
import { AUTOSAVE_MS, type SaveState } from "@/lib/playbook-doc";
import {
  ITEM_TITLE,
  SECTION_ORDER,
  blankItem,
  cleanKnowledge,
  isEmptyKnowledge,
  visibleSections,
  type Knowledge,
  type KnowledgeList,
  type KnowledgeSection,
} from "@/lib/playbook-knowledge";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

type TextKey = "icp" | "bad_fit" | "value_short" | "value_long" | "pricing" | "notes";

/** What each section shows, in order: plain texts, then one list. Fields of a list item follow. */
const LAYOUT: Record<KnowledgeSection, { texts: TextKey[]; list?: KnowledgeList; strings?: "differentiators" }> = {
  audience: { texts: ["icp", "bad_fit"], list: "personas" },
  value: { texts: ["value_short", "value_long"], strings: "differentiators" },
  proofs: { texts: [], list: "proofs" },
  competitors: { texts: [], list: "competitors" },
  triggers: { texts: [], list: "triggers" },
  pricing: { texts: ["pricing"] },
  notes: { texts: ["notes"] },
};
const ITEM_FIELDS: Record<KnowledgeList, string[]> = {
  personas: ["cares_about", "language", "measured_on"],
  proofs: ["situation", "change", "number", "tags"],
  competitors: ["win_when", "lose_when", "they_like", "landmines", "how_to_talk"],
  triggers: ["how_to_use"],
};

const labelCell = "pt-1 text-xs text-muted-foreground";
const row = "grid items-start gap-x-4 md:grid-cols-[minmax(0,11rem)_minmax(0,1fr)]";

/**
 * "Vuestra empresa" (plan §15, layer 2): who you sell to, the value story, customer stories,
 * competitors… Given once, used as context everywhere, never scored. Only sections with
 * content are on screen; the rest are one "+ Sección" away. Changes save themselves and
 * apply at once (nothing to turn on: nothing here is a rubric).
 */
export function CompanyKnowledge({ canEdit, onSaved }: { canEdit: boolean; onSaved?: () => void }) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const [load, setLoad] = useState<"loading" | "error" | "ready">("loading");
  const [knowledge, setKnowledge] = useState<Knowledge>({});
  const [added, setAdded] = useState<KnowledgeSection[]>([]);
  const [editing, setEditing] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const updatedAt = useRef<string | null>(null);
  const latest = useRef(knowledge);
  latest.current = knowledge;
  const savedRef = useRef(onSaved);
  savedRef.current = onSaved;

  const reload = useCallback(async () => {
    setLoad("loading");
    try {
      const doc = await playbooksApi.company();
      setKnowledge(doc.knowledge ?? {});
      updatedAt.current = doc.updated_at;
      setDirty(false);
      setSaveState("idle");
      setLoad("ready");
    } catch {
      setLoad("error");
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const save = useCallback(async () => {
    setSaveState("saving");
    try {
      const doc = await playbooksApi.saveCompany(cleanKnowledge(latest.current), updatedAt.current);
      updatedAt.current = doc.updated_at;
      setDirty(false);
      setSaveState("saved");
      savedRef.current?.();
    } catch (error) {
      setSaveState(errorCode(error) === "stale_knowledge" ? "stale" : "error");
    }
  }, []);

  useEffect(() => {
    if (!dirty || saveState === "stale") return;
    const timer = window.setTimeout(() => void save(), saveState === "error" ? 5000 : AUTOSAVE_MS);
    return () => window.clearTimeout(timer);
  }, [knowledge, dirty, saveState, save]);

  const edit = (next: (current: Knowledge) => Knowledge) => {
    setKnowledge(next);
    setDirty(true);
    if (saveState === "saved") setSaveState("idle");
  };

  if (load === "loading") {
    return (
      <p className="inline-flex items-center gap-2 text-sm text-muted-foreground" role="status">
        <VocifySpinner size={12} />
        {t.product.playbookEditorLoading}
      </p>
    );
  }
  if (load === "error") {
    return (
      <div className="flex items-center gap-3" role="alert">
        <p className="text-sm text-muted-foreground">{t.product.playbookEditorLoadFailed}</p>
        <Button type="button" variant="outline" size="sm" onClick={() => void reload()}>
          {t.product.retry}
        </Button>
      </div>
    );
  }

  const editable = canEdit && editing;
  const sections = visibleSections(knowledge, added);
  const missing = SECTION_ORDER.filter((section) => !sections.includes(section));
  const saveLabel =
    saveState === "saving" ? copy.saving : saveState === "saved" && !dirty ? copy.saved : saveState === "error" ? copy.saveError : saveState === "stale" ? copy.stale : null;

  const setText = (key: TextKey, value: string) => edit((current) => ({ ...current, [key]: value }));
  const listOf = (list: KnowledgeList) => ((knowledge[list] ?? []) as Record<string, unknown>[]);
  const setItem = (list: KnowledgeList, index: number, field: string, value: unknown) =>
    edit((current) => ({
      ...current,
      [list]: ((current[list] ?? []) as Record<string, unknown>[]).map((item, i) => (i === index ? { ...item, [field]: value } : item)),
    }));
  const addItem = (list: KnowledgeList) =>
    edit((current) => ({ ...current, [list]: [...((current[list] ?? []) as Record<string, unknown>[]), blankItem(list)] }));
  const removeItem = (list: KnowledgeList, index: number) =>
    edit((current) => ({ ...current, [list]: ((current[list] ?? []) as Record<string, unknown>[]).filter((_, i) => i !== index) }));

  const addButton = (onClick: () => void, label = copy.addItem) => (
    <button
      type="button"
      className={linkButton}
      onClick={onClick}
    >
      <Plus size={12} weight="light" />
      {label}
    </button>
  );

  const textRow = (key: TextKey) => {
    const value = knowledge[key] ?? "";
    if (!editable && !value.trim()) return null;
    return (
      <div key={key} className={cn(row, "py-1.5")}>
        <p className={labelCell}>{copy.fields[key]}</p>
        {editable ? (
          <InlineTextarea className="text-sm" value={value} placeholder={copy.fields[key]} aria-label={copy.fields[key]} onChange={(event) => setText(key, event.target.value)} />
        ) : (
          <p className="whitespace-pre-line pt-1 text-sm leading-relaxed text-foreground">{value}</p>
        )}
      </div>
    );
  };

  const listBlock = (list: KnowledgeList) => {
    const title = ITEM_TITLE[list];
    const items = listOf(list);
    return (
      <div className="space-y-1">
        {list === "personas" && (items.length || editable) ? <p className={cn(labelCell, "pt-2")}>{copy.fields.personas}</p> : null}
        <ul>
          {items.map((item, index) => {
            const name = String(item[title] ?? "");
            if (!editable && !name.trim()) return null;
            return (
              <li key={index} className="group space-y-0.5 border-t border-border/40 py-2.5 first:border-t-0">
                <div className="flex items-start gap-1">
                  {editable ? (
                    <InlineTextarea
                      className="flex-1 text-[15px]"
                      value={name}
                      placeholder={copy.itemTitles[list]}
                      aria-label={copy.itemTitles[list]}
                      autoFocus={!name && index === items.length - 1}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") event.preventDefault();
                      }}
                      onChange={(event) => setItem(list, index, title, event.target.value.replace(/\n/g, " "))}
                    />
                  ) : (
                    <p className="flex-1 text-[15px] text-foreground">{name}</p>
                  )}
                  {editable ? (
                    <span className="opacity-100 transition-opacity md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100">
                      <IconAction label={t.product.playbookEditorRemove} tone="danger" onClick={() => removeItem(list, index)}>
                        <Trash size={14} weight="light" />
                      </IconAction>
                    </span>
                  ) : null}
                </div>
                {ITEM_FIELDS[list].map((field) => {
                  const raw = item[field];
                  const value = Array.isArray(raw) ? raw.join(", ") : String(raw ?? "");
                  if (!editable && !value.trim()) return null;
                  return (
                    <div key={field} className={row}>
                      <p className={labelCell}>{copy.fields[field]}</p>
                      {editable ? (
                        <InlineTextarea
                          className="text-sm text-muted-foreground focus:text-foreground"
                          value={value}
                          aria-label={copy.fields[field]}
                          onChange={(event) =>
                            setItem(list, index, field, field === "tags" ? event.target.value.split(",") : event.target.value)
                          }
                        />
                      ) : (
                        <p className="whitespace-pre-line pt-1 text-sm text-muted-foreground">{value}</p>
                      )}
                    </div>
                  );
                })}
              </li>
            );
          })}
        </ul>
        {editable ? addButton(() => addItem(list)) : null}
      </div>
    );
  };

  const stringsBlock = () => {
    const items = knowledge.differentiators ?? [];
    if (!editable && !items.some((item) => item.trim())) return null;
    return (
      <div className={cn(row, "py-1.5")}>
        <p className={labelCell}>{copy.fields.differentiators}</p>
        <div className="space-y-0.5">
          {items.map((item, index) =>
            editable ? (
              <div key={index} className="group flex items-start gap-1">
                <InlineTextarea
                  className="flex-1 text-sm"
                  value={item}
                  aria-label={copy.fields.differentiators}
                  autoFocus={!item && index === items.length - 1}
                  onChange={(event) =>
                    edit((current) => ({
                      ...current,
                      differentiators: (current.differentiators ?? []).map((value, i) => (i === index ? event.target.value : value)),
                    }))
                  }
                />
                <span className="opacity-100 transition-opacity md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100">
                  <IconAction
                    label={t.product.playbookEditorRemove}
                    tone="danger"
                    onClick={() =>
                      edit((current) => ({ ...current, differentiators: (current.differentiators ?? []).filter((_, i) => i !== index) }))
                    }
                  >
                    <Trash size={14} weight="light" />
                  </IconAction>
                </span>
              </div>
            ) : item.trim() ? (
              <p key={index} className="pt-1 text-sm text-foreground">
                {item}
              </p>
            ) : null,
          )}
          {editable ? addButton(() => edit((current) => ({ ...current, differentiators: [...(current.differentiators ?? []), ""] }))) : null}
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div className="min-w-0 space-y-0.5">
          <p className={THEME_TOKENS.typography.capsLabel}>{copy.companyHint}</p>
          {canEdit ? (
            <p className={THEME_TOKENS.typography.capsLabel}>
              {copy.productNote} ·{" "}
              <Link to="/dashboard/settings/offer" className="text-foreground underline-offset-4 hover:underline">
                {copy.edit.toLowerCase()}
              </Link>
            </p>
          ) : null}
        </div>
        {canEdit ? (
          <div className="flex items-center gap-2">
            {saveLabel ? (
              saveState === "error" || saveState === "stale" ? (
                <button
                  type="button"
                  className={cn(THEME_TOKENS.typography.capsLabel, "text-warning underline-offset-4 hover:underline")}
                  onClick={() => (saveState === "stale" ? void reload() : void save())}
                >
                  {saveLabel}
                </button>
              ) : (
                <span className={THEME_TOKENS.typography.capsLabel} role="status">
                  {saveLabel}
                </span>
              )
            ) : null}
            <Button type="button" variant="ghost" size="sm" onClick={() => setEditing((value) => !value)}>
              {editing ? copy.done : copy.edit}
            </Button>
          </div>
        ) : null}
      </div>

      {isEmptyKnowledge(knowledge) && added.length === 0 ? (
        <p className={THEME_TOKENS.typography.body}>{canEdit ? copy.companyEmpty : t.product.playbookEditorReadOnlyEmpty}</p>
      ) : null}

      {sections.map((section) => {
        const layout = LAYOUT[section];
        return (
          <section key={section} className={cn("space-y-1", THEME_TOKENS.motion.fadeIn)} aria-label={copy.sections[section]}>
            <h3 className={THEME_TOKENS.typography.capsLabel}>{copy.sections[section]}</h3>
            {layout.texts.map(textRow)}
            {layout.strings ? stringsBlock() : null}
            {layout.list ? listBlock(layout.list) : null}
          </section>
        );
      })}

      {canEdit && missing.length > 0 ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className={linkButton}
            >
              <Plus size={12} weight="light" />
              {copy.addSection}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            {missing.map((section) => (
              <DropdownMenuItem
                key={section}
                onSelect={() => {
                  setAdded((current) => [...current, section]);
                  setEditing(true);
                  const list = LAYOUT[section].list;
                  if (list && listOf(list).length === 0) addItem(list);
                }}
              >
                {copy.sections[section]}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}
    </div>
  );
}
