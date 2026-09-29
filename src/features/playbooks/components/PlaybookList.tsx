import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CaretRight, Plus } from "@phosphor-icons/react";
import { useAuth } from "@/features/auth";
import { errorCode, playbooksApi, type PlaybookList as PlaybookListData } from "@/features/playbooks/api";
import { PlaybookDocument } from "@/features/playbooks/components/PlaybookDocument";
import { RuleEditor } from "@/features/playbooks/components/RuleEditor";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useLanguage } from "@/lib/i18n";
import { motionLabel } from "@/lib/motion-label";
import {
  addableTypes,
  playbookRows,
  ruleSummary,
  typeKeyFromName,
  type AppliesTo,
  type CatalogType,
  type PlaybookRow,
} from "@/lib/playbook-doc";
import { newStepKey, templateSteps, type EditorStep } from "@/lib/playbook-editor";
import type { MotionStatus } from "@/lib/playbook-setup";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

const LIST_KEY = ["playbooks"] as const;
const DEFAULT_GOALS: Record<string, string> = { discovery: "meeting_booked", closing: "proposal_and_close" };

/**
 * "Vuestro proceso" (plan §4.1): one row per call type, one open at a time. Opening a row
 * shows its playbook as a document; an empty one opens straight onto the start box.
 */
export function PlaybookList() {
  const { t, language } = useLanguage();
  const copy = t.product.pb2;
  const lang = language === "EN" ? "en" : "es";
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const features = user?.company?.features ?? [];
  const role = user?.company?.role;
  const canEdit = role === "owner" || role === "admin";
  const routing = features.includes("PLAYBOOK_ROUTING_ENABLED");
  const [openKey, setOpenKey] = useState<string | null>(null);

  const list = useQuery({ queryKey: LIST_KEY, queryFn: playbooksApi.list, retry: false });
  const catalog = useQuery({
    queryKey: ["playbooks-catalog"],
    queryFn: playbooksApi.catalog,
    enabled: routing && canEdit,
    retry: false,
    staleTime: 60 * 60 * 1000,
  });
  const stages = useQuery({
    queryKey: ["playbooks-deal-stages"],
    queryFn: playbooksApi.dealStages,
    enabled: routing && canEdit,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });

  const fetched = list.data?.motions ?? {};
  // A manager always sees the two base flows, even before anything was created.
  const motions: Record<string, MotionStatus> = canEdit ? { discovery: "missing", closing: "missing", ...fetched } : fetched;
  const details = list.data?.details ?? {};
  const types = catalog.data?.types ?? [];
  const typeOf = (key: string) => types.find((type) => type.key === key);
  const rows = playbookRows(motions, details, routing);

  const setStatus = (key: string, status: MotionStatus) =>
    queryClient.setQueryData<PlaybookListData>(LIST_KEY, (old) =>
      old ? { ...old, motions: { ...old.motions, [key]: status } } : { motions: { [key]: status } },
    );

  const name = (key: string) => {
    if (key === "closing" && "negotiation" in motions) return copy.closingDemoOnly;
    // A catalog type reads in the app's language; a company's own type keeps the name it was given.
    const localized = copy.typeLabels[key] || typeOf(key)?.label?.[lang];
    if (localized && (details[key]?.catalog ?? true)) return localized;
    return details[key]?.label || localized || motionLabel(key, t.product.motions);
  };

  const template = (key: string) => (): EditorStep[] => {
    const fromCatalog = typeOf(key)?.template?.[lang];
    if (fromCatalog?.length) return fromCatalog.map((step) => ({ key: newStepKey(), ...step }));
    return templateSteps(key, lang);
  };

  const ruleOf = (key: string): AppliesTo | null => details[key]?.applies_to ?? typeOf(key)?.applies_to ?? null;

  const saveRule = async (key: string, rule: AppliesTo) => {
    await playbooksApi.saveRule(key, rule);
    queryClient.setQueryData<PlaybookListData>(LIST_KEY, (old) => {
      if (!old) return old;
      const current = old.details?.[key] ?? { label: null, role: null, goal: null, catalog: false, applies_to: null };
      return { ...old, details: { ...old.details, [key]: { ...current, applies_to: rule, role: rule.role } } };
    });
  };

  const statusText = (row: PlaybookRow) =>
    row.status === "published" ? copy.statusLive : row.status === "missing" ? copy.statusMissing : copy.statusDraft;

  if (list.isError) {
    return (
      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} flex items-center gap-3 p-6`} role="alert">
        <p className="text-sm text-muted-foreground">{t.product.playbookEditorLoadFailed}</p>
        <Button type="button" variant="outline" size="sm" onClick={() => void list.refetch()}>
          {t.product.retry}
        </Button>
      </div>
    );
  }

  return (
    <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} px-5 py-2 md:px-7`}>
      {list.isLoading ? (
        <p className="py-4 text-sm text-muted-foreground">{t.product.playbookEditorLoading}</p>
      ) : (
        <ul>
          {rows.map((row) => {
            const open = openKey === row.key;
            const goal = details[row.key]?.goal ?? list.data?.goals?.[row.key] ?? typeOf(row.key)?.goal ?? DEFAULT_GOALS[row.key];
            return (
              <li key={row.key} className="border-t border-border/40 first:border-t-0">
                <button
                  type="button"
                  className="flex w-full items-center gap-3 py-4 text-left"
                  aria-expanded={open}
                  onClick={() => setOpenKey(open ? null : row.key)}
                >
                  <span className="min-w-0">
                    <span className="text-[15px] text-foreground">{name(row.key)}</span>
                    {row.role && row.role !== "any" ? (
                      <span className={cn(THEME_TOKENS.typography.capsLabel, "ml-2")}>{copy.ruleRoles[row.role]}</span>
                    ) : null}
                    {row.unrouted && canEdit ? (
                      <span className="block text-xs text-warning">{copy.unrouted}</span>
                    ) : null}
                  </span>
                  <span className="ml-auto flex shrink-0 items-center gap-3">
                    {row.status === "missing" && canEdit && !open ? (
                      <span className="rounded-full border border-border px-3 py-1 text-[13px] text-foreground">{copy.create}</span>
                    ) : (
                      <span className={THEME_TOKENS.typography.capsLabel}>{statusText(row)}</span>
                    )}
                    <CaretRight
                      size={14}
                      weight="light"
                      className={cn("text-muted-foreground transition-transform duration-150", open && "rotate-90")}
                    />
                  </span>
                </button>
                {open ? (
                  <div className={cn("pb-7 pt-1", THEME_TOKENS.motion.fadeIn)}>
                    <RowDocument
                      motionKey={row.key}
                      canEdit={canEdit}
                      status={row.status}
                      template={template(row.key)}
                      onStatus={(status) => setStatus(row.key, status)}
                      meta={
                        <>
                          {goal && copy.goals[goal] ? <p className={THEME_TOKENS.typography.capsLabel}>{copy.goals[goal]}</p> : null}
                          {routing && canEdit ? (
                            <RuleLine
                              rule={ruleOf(row.key)}
                              stages={stages.data?.stages ?? []}
                              onSave={(rule) => saveRule(row.key, rule)}
                            />
                          ) : null}
                        </>
                      }
                    />
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
      {routing && canEdit && !list.isLoading ? (
        <div className="border-t border-border/40 py-3">
          <AddType
            catalog={addableTypes(types, motions)}
            stages={stages.data?.stages ?? []}
            onAdded={(key) => {
              void queryClient.invalidateQueries({ queryKey: LIST_KEY });
              setOpenKey(key);
            }}
          />
        </div>
      ) : null}
    </div>
  );
}

/** Per open row, so the insights query only runs for the playbook on screen. */
function RowDocument({
  motionKey,
  canEdit,
  status,
  template,
  meta,
  onStatus,
}: {
  motionKey: string;
  canEdit: boolean;
  status: MotionStatus;
  template: () => EditorStep[];
  meta: React.ReactNode;
  onStatus: (status: MotionStatus) => void;
}) {
  const insights = useQuery({
    queryKey: ["playbook-insights", motionKey],
    queryFn: () => playbooksApi.insights(motionKey, "month"),
    enabled: canEdit && status === "published",
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
  return (
    <PlaybookDocument
      motionKey={motionKey}
      canEdit={canEdit}
      meta={meta}
      template={template}
      insights={insights.data ?? null}
      onStatus={onStatus}
    />
  );
}

function RuleLine({
  rule,
  stages,
  onSave,
}: {
  rule: AppliesTo | null;
  stages: { id: string; label: string }[];
  onSave: (rule: AppliesTo) => Promise<void>;
}) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);
  const summary = ruleSummary(rule, {
    roles: copy.ruleRoles,
    channels: copy.ruleChannels,
    contacts: copy.ruleContacts,
    stages: copy.ruleStages,
    join: copy.ruleJoin,
  });
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <p className={THEME_TOKENS.typography.capsLabel}>
        {summary ? `${copy.ruleLabel}: ${summary} · ` : `${copy.ruleNone} · `}
        <PopoverTrigger asChild>
          <button type="button" className="text-foreground underline-offset-4 hover:underline">
            {summary ? copy.ruleChange : copy.ruleAdd}
          </button>
        </PopoverTrigger>
        {failed ? <span className="ml-2 text-destructive">{copy.ruleFailed}</span> : null}
      </p>
      <PopoverContent align="start" className="w-[22rem] max-w-[calc(100vw-2rem)]">
        <RuleEditor
          value={rule}
          stages={stages}
          saving={saving}
          onSave={(next) => {
            setSaving(true);
            setFailed(false);
            void onSave(next)
              .then(() => setOpen(false))
              .catch(() => setFailed(true))
              .finally(() => setSaving(false));
          }}
        />
      </PopoverContent>
    </Popover>
  );
}

function AddType({
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
      const code = errorCode(caught);
      setError(code === "rule_required" ? copy.ruleNone : copy.newTypeFailed);
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
        <button
          type="button"
          className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-sm text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
        >
          <Plus size={12} weight="light" />
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
