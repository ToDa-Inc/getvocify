import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ArrowUpRight, SquarePen, Plus, Sparkles, Swords, Trophy, Users, type LucideIcon as Icon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { TabCount, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { useTeamAdherence } from "@/features/head-of-sales/useTeamAdherence";
import { errorCode, playbooksApi, type CompanyFillScope, type FillSource } from "@/features/playbooks/api";
import { CompleteButton, DocRow, ItemMenu } from "@/features/playbooks/components/DocParts";
import { FillBox } from "@/features/playbooks/components/FillBox";
import { InlineTextarea } from "@/features/playbooks/components/InlineField";
import { SaveStatus } from "@/features/playbooks/components/SaveStatus";
import { CompanyIcon } from "@/features/playbooks/icons";
import { itemBody, itemTitle, linkButton } from "@/features/playbooks/styles";
import { HOS_DEFAULT_PERIOD } from "@/lib/head-of-sales";
import { useLanguage } from "@/lib/i18n";
import { AUTOSAVE_MS, type SaveState } from "@/lib/playbook-doc";
import {
  COMPANY_TABS,
  COMPANY_TAB_ORDER,
  ITEM_LINE,
  ITEM_TITLE,
  blankItem,
  cleanKnowledge,
  suggestedCompetitors,
  tabCount,
  tabFilled,
  type CompanyTab,
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
const LONG_TEXTS: TextKey[] = ["value_long", "notes", "pricing"];
const TAB_ICONS: Record<CompanyTab, Icon> = {
  customer: Users,
  value: Sparkles,
  proofs: Trophy,
  competitors: Swords,
  notes: SquarePen,
};
const MAX_SUGGESTED = 5;

/**
 * "Vuestra empresa" (plan §15, layer 2): who you sell to, the offer, customer stories,
 * competitors… Given once, used as context everywhere, never scored. Five tabs, one pattern:
 * every item is a bold name and one line, edited where it is read; what is missing Vocify writes
 * ("Completar", or anything said to "Dile a Vocify"). Changes save themselves and apply at once
 * (nothing here is a rubric).
 */
export function CompanyKnowledge({ canEdit, onSaved }: { canEdit: boolean; onSaved?: () => void }) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const [load, setLoad] = useState<"loading" | "error" | "ready">("loading");
  const [knowledge, setKnowledge] = useState<Knowledge>({});
  const [dirty, setDirty] = useState(false);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [tab, setTab] = useState<CompanyTab>("customer");
  // The item that was just added, to focus its name.
  const [focus, setFocus] = useState<string | null>(null);
  const [filling, setFilling] = useState<string | null>(null);
  const updatedAt = useRef<string | null>(null);
  const latest = useRef(knowledge);
  latest.current = knowledge;
  const savedRef = useRef(onSaved);
  savedRef.current = onSaved;
  // Competitors the team's calls mention: the Sales process page already reads this (same cache).
  const adherence = useTeamAdherence(HOS_DEFAULT_PERIOD, "all");

  const adopt = useCallback((doc: { knowledge?: Knowledge | null; updated_at: string | null }) => {
    setKnowledge(doc.knowledge ?? {});
    updatedAt.current = doc.updated_at;
    setDirty(false);
  }, []);

  const reload = useCallback(async () => {
    setLoad("loading");
    try {
      adopt(await playbooksApi.company());
      setSaveState("idle");
      setLoad("ready");
    } catch {
      setLoad("error");
    }
  }, [adopt]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const save = useCallback(async (): Promise<boolean> => {
    setSaveState("saving");
    try {
      const doc = await playbooksApi.saveCompany(cleanKnowledge(latest.current), updatedAt.current);
      updatedAt.current = doc.updated_at;
      setDirty(false);
      setSaveState("saved");
      savedRef.current?.();
      return true;
    } catch (error) {
      setSaveState(errorCode(error) === "stale_knowledge" ? "stale" : "error");
      return false;
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

  /**
   * "Dile a Vocify": what is typed is saved first, then the request goes to Vocify, which saves
   * the result at once; one toast says what changed, with an undo. Throws, so the box can say why.
   */
  const fill = async (source: FillSource, target: string, scope?: CompanyFillScope) => {
    setFilling(target);
    try {
      if (dirty && !(await save())) throw new Error("unsaved");
      const before = latest.current;
      const result = await playbooksApi.fillCompany(source, updatedAt.current, scope);
      if (!result.filled.length) {
        toast(result.summary || copy.fillNothing);
        return;
      }
      adopt(result);
      setSaveState("saved");
      savedRef.current?.();
      toast(result.summary || copy.fillDone, { action: { label: copy.undo, onClick: () => edit(() => before) } });
    } catch (error) {
      if (errorCode(error) === "stale_knowledge") setSaveState("stale");
      throw error;
    } finally {
      setFilling(null);
    }
  };
  /** A "Completar": the request is written for the manager and only that part may change. */
  const ask = (request: string, target: string, scope: CompanyFillScope) => {
    void fill({ kind: "text", payload: request }, target, scope).catch(() => toast.error(copy.fillFailed));
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

  const editable = canEdit;
  // A rep only sees the tabs that say something.
  const tabs = editable ? COMPANY_TAB_ORDER : COMPANY_TAB_ORDER.filter((item) => tabFilled(knowledge, item));
  const activeTab = tabs.includes(tab) ? tab : tabs[0];
  const busy = filling !== null;

  const listOf = (list: KnowledgeList) => (knowledge[list] ?? []) as Record<string, string>[];
  const setItem = (list: KnowledgeList, index: number, field: string, value: string) =>
    edit((current) => ({
      ...current,
      [list]: ((current[list] ?? []) as Record<string, string>[]).map((item, i) => (i === index ? { ...item, [field]: value } : item)),
    }));
  const addItem = (list: KnowledgeList, name = "") => {
    const index = listOf(list).length;
    edit((current) => ({
      ...current,
      [list]: [...((current[list] ?? []) as Record<string, string>[]), { ...blankItem(list), [ITEM_TITLE[list]]: name }],
    }));
    if (!name) setFocus(`${list}:${index}`);
  };
  const removeItem = (list: KnowledgeList, index: number) =>
    edit((current) => ({ ...current, [list]: ((current[list] ?? []) as Record<string, string>[]).filter((_, i) => i !== index) }));

  const dot = <span className="mt-2 h-1.5 w-1.5 rounded-full bg-beige" aria-hidden />;

  /** A text field as an item: its name in bold and the text as its line. */
  const textRow = (key: TextKey, section: KnowledgeSection) => {
    const value = knowledge[key] ?? "";
    if (!editable && !value.trim()) return null;
    return (
      <DocRow key={key} lead={dot} title={<p className={itemTitle}>{copy.fields[key]}</p>}>
        {editable ? (
          <InlineTextarea
            className={itemBody}
            value={value}
            placeholder={copy.fieldHints[key]}
            aria-label={copy.fields[key]}
            onKeyDown={(event) => {
              if (!LONG_TEXTS.includes(key) && event.key === "Enter") event.preventDefault();
            }}
            onChange={(event) => edit((current) => ({ ...current, [key]: event.target.value }))}
          />
        ) : (
          <p className={cn(itemBody, "whitespace-pre-line")}>{value}</p>
        )}
        {/* Free notes are the manager's own: nothing for Vocify to complete. */}
        {editable && !value.trim() && key !== "notes" ? (
          <div className="pt-1">
            <CompleteButton
              label={copy.complete}
              pending={filling === key}
              disabled={busy}
              onClick={() =>
                ask(
                  copy.reqTab.replace("{section}", copy.sections[section]).replace("{fields}", copy.fields[key]),
                  key,
                  { texts: [key] },
                )
              }
            />
          </div>
        ) : null}
      </DocRow>
    );
  };

  const differentiators = () => {
    const items = knowledge.differentiators ?? [];
    if (!editable && !items.some((item) => item.trim())) return null;
    const update = (next: (list: string[]) => string[]) => edit((current) => ({ ...current, differentiators: next(current.differentiators ?? []) }));
    return (
      <DocRow key="differentiators" lead={dot} title={<p className={itemTitle}>{copy.fields.differentiators}</p>}>
        <ul className="space-y-0.5">
          {items.map((item, index) => (
            <li key={index} className="group/diff flex items-start gap-2">
              <span className="mt-2.5 h-1 w-1 shrink-0 rounded-full bg-muted-foreground/50" aria-hidden />
              {editable ? (
                <InlineTextarea
                  className={cn(itemBody, "flex-1")}
                  value={item}
                  placeholder={copy.fieldHints.differentiators}
                  aria-label={copy.fields.differentiators}
                  autoFocus={focus === `differentiators:${index}`}
                  onChange={(event) => update((list) => list.map((value, i) => (i === index ? event.target.value : value)))}
                  onBlur={() => {
                    if (!items[index]?.trim()) update((list) => list.filter((_, i) => i !== index));
                  }}
                />
              ) : (
                <p className={itemBody}>{item}</p>
              )}
            </li>
          ))}
        </ul>
        {editable ? (
          <Button
            type="button"
            variant="quiet"
            size="text"
            onClick={() => {
              setFocus(`differentiators:${items.length}`);
              update((list) => [...list, ""]);
            }}
            className="gap-1"
          >
            <Plus size={12} strokeWidth={1.5} />
            {copy.addDifferentiator}
          </Button>
        ) : null}
      </DocRow>
    );
  };

  const listBlock = (list: KnowledgeList, section: KnowledgeSection, withTitle: boolean) => {
    const title = ITEM_TITLE[list];
    const lineKey = ITEM_LINE[list];
    const items = listOf(list);
    const named = items.filter((item) => String(item[title] ?? "").trim());
    if (!editable && named.length === 0) return null;
    const known = new Set(named.map((item) => String(item[title]).trim().toLowerCase()));
    const suggested =
      editable && list === "competitors" ? suggestedCompetitors(adherence.data?.competitor_mentions, known).slice(0, MAX_SUGGESTED) : [];
    return (
      <div key={list}>
        {withTitle ? <h4 className={cn(THEME_TOKENS.typography.groupTitle, "pt-4")}>{copy.fields[list] ?? copy.sections[section]}</h4> : null}
        {items.length === 0 && editable ? <p className="pt-2 text-sm text-muted-foreground">{copy.listEmpty[list]}</p> : null}
        <ul>
          {items.map((item, index) => {
            const name = String(item[title] ?? "");
            const line = String(item[lineKey] ?? "");
            if (!editable && !name.trim()) return null;
            const target = `${list}:${index}`;
            return (
              <DocRow
                key={index}
                lead={dot}
                title={
                  editable ? (
                    <InlineTextarea
                      className={itemTitle}
                      value={name}
                      placeholder={copy.fieldHints[title === "name" ? `${list}_name` : title] ?? copy.itemTitles[list]}
                      aria-label={copy.itemTitles[list]}
                      autoFocus={focus === target}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") event.preventDefault();
                      }}
                      onChange={(event) => setItem(list, index, title, event.target.value.replace(/\n/g, " "))}
                    />
                  ) : (
                    <p className={itemTitle}>{name}</p>
                  )
                }
                side={
                  editable ? (
                    <ItemMenu
                      label={copy.itemMenu.replace("{name}", name || copy.itemTitles[list])}
                      actions={[{ label: t.product.playbookEditorRemove, danger: true, onSelect: () => removeItem(list, index) }]}
                    />
                  ) : null
                }
              >
                {editable ? (
                  <InlineTextarea
                    className={itemBody}
                    value={line}
                    placeholder={copy.fieldHints[lineKey]}
                    aria-label={copy.fields[lineKey]}
                    onChange={(event) => setItem(list, index, lineKey, event.target.value)}
                  />
                ) : line ? (
                  <p className={itemBody}>{line}</p>
                ) : null}
                {editable && name.trim() && !line.trim() ? (
                  <div className="pt-1">
                    <CompleteButton
                      label={copy.complete}
                      pending={filling === target}
                      disabled={busy}
                      onClick={() =>
                        ask(
                          copy.reqItem
                            .replace("{name}", name)
                            .replace("{section}", copy.sections[section])
                            .replace("{fields}", copy.fields[lineKey]),
                          target,
                          { list, name },
                        )
                      }
                    />
                  </div>
                ) : null}
              </DocRow>
            );
          })}
        </ul>
        {editable ? (
          <div className="flex flex-wrap items-center gap-1 pt-2">
            <Button type="button" variant="quiet" size="text" onClick={() => addItem(list)} className="gap-1">
              <Plus size={12} strokeWidth={1.5} />
              {copy.addItemOf[list]}
            </Button>
            {suggested.length ? (
              <>
                <span className="pl-2 text-xs text-muted-foreground">{copy.mentionedInCalls}:</span>
                {suggested.map((mention) => (
                  <Button
                    key={mention.name}
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => addItem(list, mention.name)}
                    className="h-auto px-2.5 py-0.5 text-xs"
                  >
                    + {mention.name} · {mention.count}
                  </Button>
                ))}
              </>
            ) : null}
          </div>
        ) : null}
      </div>
    );
  };

  const section = (key: KnowledgeSection, withTitle: boolean) => {
    const layout = LAYOUT[key];
    const rows = [...layout.texts.map((text) => textRow(text, key)), layout.strings ? differentiators() : null].filter(Boolean);
    return (
      <section key={key} aria-label={copy.sections[key]}>
        {withTitle && rows.length > 0 ? <h4 className={cn(THEME_TOKENS.typography.groupTitle, "pt-4")}>{copy.sections[key]}</h4> : null}
        {rows.length > 0 ? <ul>{rows}</ul> : null}
        {layout.list ? listBlock(layout.list, key, withTitle || layout.texts.length > 0) : null}
      </section>
    );
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
        <div className="min-w-0 space-y-1">
          <h3 className={cn(THEME_TOKENS.typography.panelTitle, "flex items-center gap-2.5")}>
            <CompanyIcon size={20} strokeWidth={1.5} className="text-muted-foreground" />
            {copy.companyTitle}
          </h3>
          <p className={THEME_TOKENS.typography.capsLabel}>
            {copy.companyHint}
            {canEdit ? (
              <>
                {" · "}
                <Link to="/dashboard/settings/offer" className="inline-flex items-center gap-0.5 text-foreground underline-offset-4 hover:underline">
                  {copy.productLink}
                  <ArrowUpRight size={11} strokeWidth={1.75} />
                </Link>
              </>
            ) : null}
          </p>
        </div>
        {canEdit ? (
          <div className="self-end sm:self-start">
            <SaveStatus state={saveState} dirty={dirty} onRetry={() => void save()} onReload={() => void reload()} />
          </div>
        ) : null}
      </div>

      {tabs.length === 0 ? (
        <p className={THEME_TOKENS.typography.body}>{t.product.playbookEditorReadOnlyEmpty}</p>
      ) : (
        <Tabs value={activeTab} onValueChange={(value) => setTab(value as CompanyTab)}>
          <TabsList aria-label={copy.companyTitle}>
            {tabs.map((item) => {
              const TabIcon = TAB_ICONS[item];
              return (
                <TabsTrigger key={item} value={item}>
                  <TabIcon size={15} strokeWidth={1.5} />
                  {copy.companyTabs[item]}
                  <TabCount value={tabCount(knowledge, item)} />
                </TabsTrigger>
              );
            })}
          </TabsList>
          {tabs.map((item) => (
            <TabsContent key={item} value={item}>
              {COMPANY_TABS[item].map((key) => section(key, COMPANY_TABS[item].length > 1))}
            </TabsContent>
          ))}
        </Tabs>
      )}

      {canEdit ? (
        // Floats at the bottom of the screen: the list scrolls under it (glass), always one step away.
        <div className="sticky bottom-4 z-10 pt-2">
          <FillBox placeholder={copy.fillCompanyPlaceholder} busy={busy} submit={(source) => fill(source, "box")} />
        </div>
      ) : null}
    </div>
  );
}
