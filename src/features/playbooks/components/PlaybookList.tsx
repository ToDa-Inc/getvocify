import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CaretRight, DotsThree, Plus } from "@phosphor-icons/react";
import { toast } from "sonner";
import { useAuth } from "@/features/auth";
import { errorCode, playbooksApi, type PlaybookList as PlaybookListData } from "@/features/playbooks/api";
import { CompanyKnowledge } from "@/features/playbooks/components/CompanyKnowledge";
import { PlaybookDocument, type Flush } from "@/features/playbooks/components/PlaybookDocument";
import { PlaybookStart, type SourceInput } from "@/features/playbooks/components/PlaybookStart";
import { RuleEditor } from "@/features/playbooks/components/RuleEditor";
import { Button } from "@/components/ui/button";
import { ConfirmAction } from "@/components/ui/confirm-action";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Switch } from "@/components/ui/switch";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { useLanguage } from "@/lib/i18n";
import { motionLabel } from "@/lib/motion-label";
import {
  addableTypes,
  countLine,
  editorFromStructure,
  nothingYet,
  optimisticStatus,
  switchState,
  pendingKeys,
  playbookRows,
  rowState,
  ruleNeeded,
  ruleSummary,
  typeKeyFromName,
  type AppliesTo,
  type CatalogType,
} from "@/lib/playbook-doc";
import { draftPayload, newStepKey, templateSteps, type EditorStep } from "@/lib/playbook-editor";
import { isEmptyKnowledge, knowledgeSummary } from "@/lib/playbook-knowledge";
import type { MotionStatus } from "@/lib/playbook-setup";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

const LIST_KEY = ["playbooks"] as const;
/** Always listed for a manager, so deleting one empties it rather than hiding it. */
const BASE_KEYS = ["discovery", "closing"];
const COMPANY_KEY = ["playbook-company"] as const;
/** The "Vuestra empresa" row's key, next to the call types' motion keys. */
const COMPANY_ROW = "__company";
const DEFAULT_GOALS: Record<string, string> = { discovery: "meeting_booked", closing: "proposal_and_close" };
const linkButton =
  "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-sm text-muted-foreground hover:bg-secondary/60 hover:text-foreground";

type Fallback = { candidates: { key: string; label: string }[]; input: SourceInput };

/**
 * "Vuestro proceso" (plan §14). One way in for the whole company: give Vocify the playbook
 * (text, file or voice) and it comes back split by call type. Each call type is a row that
 * opens as a document. Nothing reaches the team until "Activar para el equipo", which turns
 * every pending change on at once.
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
  const [intakeOpen, setIntakeOpen] = useState(false);
  const [browse, setBrowse] = useState(false);
  const [found, setFound] = useState<number | null>(null);
  const [foundCompany, setFoundCompany] = useState<string | null>(null);
  const [fallback, setFallback] = useState<Fallback | null>(null);
  const [intakeNotice, setIntakeNotice] = useState<string | null>(null);
  const [picking, setPicking] = useState<string | null>(null);
  const [activating, setActivating] = useState(false);
  const [docVersion, setDocVersion] = useState(0);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [deleteKey, setDeleteKey] = useState<string | null>(null);
  const flushes = useRef(new Map<string, Flush>());

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
  const company = useQuery({ queryKey: COMPANY_KEY, queryFn: playbooksApi.company, retry: false });
  const companySummary = knowledgeSummary(company.data?.knowledge, copy.summary);
  const empty =
    canEdit && list.isSuccess && nothingYet(motions, details) && !company.isLoading && isEmptyKnowledge(company.data?.knowledge);
  const showIntake = canEdit && ((empty && !browse) || intakeOpen);
  const pending = pendingKeys(motions, details);

  const refresh = () => queryClient.invalidateQueries({ queryKey: LIST_KEY });

  /** The server's answer to a pause/resume/delete/restore is the new list: take it as is. */
  const adoptList = (data: PlaybookListData) => queryClient.setQueryData<PlaybookListData>(LIST_KEY, data);

  /** The row switch. Flips at once, confirms with the server, rolls back on failure; the toast
   * offers the opposite action, so a misclick costs one click. */
  const toggle = async (key: string, on: boolean) => {
    const action = on ? "resume" : "pause";
    const label = name(key);
    setBusyKey(key);
    queryClient.setQueryData<PlaybookListData>(LIST_KEY, (old) => {
      if (!old) return old;
      const next = optimisticStatus(action, old.motions[key] ?? "missing");
      return next ? { ...old, motions: { ...old.motions, [key]: next } } : old;
    });
    try {
      adoptList(await (on ? playbooksApi.resume(key) : playbooksApi.pause(key)));
      setDocVersion((version) => version + 1);
      toast((on ? copy.resumedToast : copy.pausedToast).replace("{name}", label), {
        action: { label: copy.undo, onClick: () => void toggle(key, !on) },
      });
    } catch {
      await refresh();
      toast.error(copy.actionFailed);
    } finally {
      setBusyKey(null);
    }
  };

  /** Delete is soft on the server (calls already scored keep their mark), so it can be undone. */
  const remove = async (key: string) => {
    const label = name(key);
    setBusyKey(key);
    try {
      adoptList(await playbooksApi.remove(key));
      flushes.current.delete(key);
      if (openKey === key) setOpenKey(null);
      toast(copy.deletedToast.replace("{name}", label), {
        action: {
          label: copy.undo,
          onClick: () =>
            void playbooksApi
              .restore(key)
              .then((data) => {
                adoptList(data);
                setDocVersion((version) => version + 1);
              })
              .catch(() => toast.error(copy.actionFailed)),
        },
      });
    } catch {
      toast.error(copy.actionFailed);
    } finally {
      setBusyKey(null);
      setDeleteKey(null);
    }
  };

  const name = (key: string) => {
    if (key === "closing" && "negotiation" in motions) return copy.closingDemoOnly;
    // A catalog type reads in the app's language; a company's own type keeps its name.
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
    await refresh();
  };

  const closeIntake = () => {
    setIntakeOpen(false);
    setFallback(null);
    setIntakeNotice(null);
  };

  /** The whole document at once: Vocify splits it by call type and saves each as a draft. */
  const intake = async (input: SourceInput) => {
    setIntakeNotice(null);
    setFallback(null);
    const result = await playbooksApi.intake(input.kind, input.payload, input.name);
    if (result.fallback) {
      setFallback({ candidates: result.candidates, input });
      return;
    }
    const companyFilled = (result.company?.filled.length ?? 0) > 0;
    if (result.types.length === 0 && !companyFilled) {
      setIntakeNotice(copy.reasonNoProcess);
      return;
    }
    if (result.company) queryClient.setQueryData(COMPANY_KEY, result.company);
    await refresh();
    setFound(result.types.length);
    setFoundCompany(companyFilled ? knowledgeSummary(result.company?.knowledge, copy.summary) : null);
    setOpenKey(result.types.length === 1 ? result.types[0].sales_motion_key : null);
    closeIntake();
    setBrowse(true);
  };

  /** Vocify couldn't split it: the person says which call it is, and that one is structured. */
  const pickType = async (key: string) => {
    if (!fallback) return;
    setPicking(key);
    try {
      const { input } = fallback;
      const result = await playbooksApi.structure(key, input.kind, input.payload, input.name);
      const next = editorFromStructure(result, newStepKey);
      if (next.steps.length === 0) {
        setIntakeNotice(copy.reasonNoProcess);
        return;
      }
      await playbooksApi.saveDraft(key, {
        ...draftPayload(next.steps, next.objections, next.qualification),
        source_id: result.source?.id ?? null,
      });
      await refresh();
      setFound(1);
      setFoundCompany(null);
      setOpenKey(key);
      closeIntake();
      setBrowse(true);
    } catch (error) {
      const code = errorCode(error);
      setIntakeNotice((code && copy.readErrors[code]) || copy.structureFailed);
    } finally {
      setPicking(null);
    }
  };

  /** One action for the page: save what is being typed, then turn every pending change on. */
  const activate = async () => {
    setActivating(true);
    try {
      const saved = await Promise.all([...flushes.current.values()].map((flush) => flush()));
      if (saved.some((ok) => !ok)) throw new Error("unsaved");
      const fresh = await list.refetch();
      const data = fresh.data ?? list.data;
      const keys = pendingKeys(
        canEdit ? { discovery: "missing", closing: "missing", ...(data?.motions ?? {}) } : data?.motions ?? {},
        data?.details ?? {},
      );
      for (const key of keys) {
        const result = await playbooksApi.publish(key);
        if (result.motions[key] !== "published") throw new Error("publish");
      }
      await refresh();
      setFound(null);
      setFoundCompany(null);
      setDocVersion((version) => version + 1);
      toast.success(copy.activated);
    } catch (error) {
      toast.error(errorCode(error) === "contradiction" ? t.product.playbookContradiction : copy.activateFailed);
    } finally {
      setActivating(false);
    }
  };

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

  if (list.isLoading) {
    return (
      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6`}>
        <p className="inline-flex items-center gap-2 text-sm text-muted-foreground" role="status">
          <VocifySpinner size={12} />
          {t.product.playbookEditorLoading}
        </p>
      </div>
    );
  }

  return (
    <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} px-5 md:px-7`}>
      {showIntake ? (
        <div className={cn("space-y-4 py-6", !empty && "border-b border-border/40", THEME_TOKENS.motion.fadeIn)}>
          <div className="space-y-1">
            <h3 className={THEME_TOKENS.typography.sectionTitle}>{copy.intakeTitle}</h3>
            <p className="text-sm text-muted-foreground">{copy.intakeHint}</p>
          </div>
          <PlaybookStart
            submit={intake}
            minHeight="min-h-[200px]"
            placeholder={copy.intakePlaceholder}
            readingLabel={copy.intakeReading}
            onTemplate={empty ? () => setBrowse(true) : undefined}
            onCancel={empty ? undefined : closeIntake}
          />
          {intakeNotice ? (
            <p className="text-sm text-destructive" role="alert">
              {intakeNotice}
            </p>
          ) : null}
          {fallback ? (
            <div className={cn("space-y-2", THEME_TOKENS.motion.fadeIn)}>
              <p className="text-sm text-foreground">{copy.fallbackAsk}</p>
              <div className="flex flex-wrap gap-2">
                {fallback.candidates.map((candidate) => (
                  <Button
                    key={candidate.key}
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={picking !== null}
                    onClick={() => void pickType(candidate.key)}
                  >
                    {picking === candidate.key ? <VocifySpinner size={12} /> : null}
                    <span className={picking === candidate.key ? "ml-1.5" : undefined}>{name(candidate.key)}</span>
                  </Button>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      {empty && !browse ? null : (
        <>
          {found || foundCompany ? (
            <div className={cn("space-y-0.5 pt-5 text-sm text-foreground", THEME_TOKENS.motion.fadeIn)} role="status">
              {found ? <p>{found === 1 ? copy.foundOne : copy.foundMany.replace("{count}", String(found))}</p> : null}
              {foundCompany ? <p className="text-muted-foreground">{copy.foundCompany.replace("{summary}", foundCompany)}</p> : null}
            </div>
          ) : null}
          <ul className="py-1">
            {/* Shared by every call type: who you sell to, the value story, stories, competitors. */}
            <li className="border-t border-border/40 first:border-t-0">
              <button
                type="button"
                className="flex w-full items-center gap-3 py-4 text-left"
                aria-expanded={openKey === COMPANY_ROW}
                onClick={() => setOpenKey(openKey === COMPANY_ROW ? null : COMPANY_ROW)}
              >
                <span className="text-[15px] text-foreground">{copy.companyTitle}</span>
                <span className="ml-auto flex shrink-0 items-center gap-3">
                  <span className={cn(THEME_TOKENS.typography.capsLabel, "hidden truncate sm:inline")}>
                    {companySummary ?? copy.statusMissing}
                  </span>
                  <CaretRight
                    size={14}
                    weight="light"
                    className={cn("text-muted-foreground transition-transform duration-150", openKey === COMPANY_ROW && "rotate-90")}
                  />
                </span>
              </button>
              {openKey === COMPANY_ROW ? (
                <div className={cn("pb-7 pt-1", THEME_TOKENS.motion.fadeIn)}>
                  <CompanyKnowledge
                    key={docVersion}
                    canEdit={canEdit}
                    onSaved={() => void queryClient.invalidateQueries({ queryKey: COMPANY_KEY })}
                  />
                </div>
              ) : null}
            </li>
            {rows.map((row) => {
              const open = openKey === row.key;
              const detail = details[row.key];
              const state = rowState(row.status, detail);
              const counts = countLine(detail, copy);
              const goal = detail?.goal ?? list.data?.goals?.[row.key] ?? typeOf(row.key)?.goal ?? DEFAULT_GOALS[row.key];
              return (
                <li key={row.key} className="group/row border-t border-border/40 first:border-t-0">
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      className="flex min-w-0 flex-1 items-center gap-3 py-4 text-left"
                      aria-expanded={open}
                      onClick={() => setOpenKey(open ? null : row.key)}
                    >
                      <span className="min-w-0">
                        <span className="text-[15px] text-foreground">{name(row.key)}</span>
                        {row.role && row.role !== "any" ? (
                          <span className={cn(THEME_TOKENS.typography.capsLabel, "ml-2")}>{copy.ruleRoles[row.role]}</span>
                        ) : null}
                        {row.unrouted && canEdit ? <span className="block text-xs text-warning">{copy.unrouted}</span> : null}
                      </span>
                      <span className="ml-auto flex shrink-0 items-center gap-3">
                        {state === "empty" ? (
                          canEdit && !open ? (
                            <span className="rounded-full border border-border px-3 py-1 text-[13px] text-foreground">{copy.create}</span>
                          ) : (
                            <span className={THEME_TOKENS.typography.capsLabel}>{copy.statusMissing}</span>
                          )
                        ) : (
                          <span className={cn(THEME_TOKENS.typography.capsLabel, "inline-flex items-center gap-2")}>
                            <span className="hidden sm:inline">{counts}</span>
                            <span
                              className={cn(
                                "h-1.5 w-1.5 rounded-full transition-colors",
                                state === "live" ? "bg-success" : state === "paused" ? "bg-muted-foreground/40" : "bg-beige",
                              )}
                              aria-hidden
                            />
                            {state === "live" ? copy.statusLive : state === "paused" ? copy.statusPaused : copy.statusPending}
                          </span>
                        )}
                      </span>
                    </button>
                    {canEdit && switchState(state) !== null ? (
                      <Switch
                        // Off has to read as "off", not as missing: the default unchecked track is near-white.
                        className="data-[state=unchecked]:bg-muted-foreground/30"
                        checked={Boolean(switchState(state))}
                        disabled={busyKey === row.key}
                        aria-label={copy.switchLabel.replace("{name}", name(row.key))}
                        onCheckedChange={(on) => void toggle(row.key, on)}
                      />
                    ) : null}
                    {/* Open with content, the document's own "···" has "Eliminar": one menu at a time. */}
                    {canEdit && !(open && state !== "empty") && (state !== "empty" || !BASE_KEYS.includes(row.key)) ? (
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <button
                            type="button"
                            aria-label={copy.rowMenu.replace("{name}", name(row.key))}
                            className={cn(
                              THEME_TOKENS.interaction.iconButton,
                              "h-8 w-8 md:opacity-0 md:group-hover/row:opacity-100 md:focus-visible:opacity-100 data-[state=open]:opacity-100",
                            )}
                          >
                            <DotsThree size={18} weight="bold" />
                          </button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem className="text-destructive focus:text-destructive" onSelect={() => setDeleteKey(row.key)}>
                            {copy.deleteAction}
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    ) : null}
                    <button
                      type="button"
                      tabIndex={-1}
                      aria-hidden
                      className="py-4"
                      onClick={() => setOpenKey(open ? null : row.key)}
                    >
                      <CaretRight
                        size={14}
                        weight="light"
                        className={cn("text-muted-foreground transition-transform duration-150", open && "rotate-90")}
                      />
                    </button>
                  </div>
                  {open ? (
                    <div className={cn("pb-7 pt-1", THEME_TOKENS.motion.fadeIn)}>
                      <RowDocument
                        key={`${row.key}-${docVersion}`}
                        motionKey={row.key}
                        canEdit={canEdit}
                        live={state === "live"}
                        template={template(row.key)}
                        onSaved={() => void refresh()}
                        onDelete={state === "empty" && BASE_KEYS.includes(row.key) ? undefined : () => setDeleteKey(row.key)}
                        registerFlush={(flush) => {
                          if (flush) flushes.current.set(row.key, flush);
                          else flushes.current.delete(row.key);
                        }}
                        meta={
                          <>
                            {goal && copy.goals[goal] ? <p className={THEME_TOKENS.typography.capsLabel}>{copy.goals[goal]}</p> : null}
                            {state === "paused" ? <p className={THEME_TOKENS.typography.capsLabel}>{copy.pausedLine}</p> : null}
                            {canEdit && ruleNeeded(rows, row.key, routing) ? (
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
          {canEdit ? (
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border/40 py-3">
              <div className="flex flex-wrap items-center gap-1">
                {!showIntake ? (
                  <button type="button" className={linkButton} onClick={() => setIntakeOpen(true)}>
                    <Plus size={12} weight="light" />
                    {copy.addFromDoc}
                  </button>
                ) : null}
                {routing ? (
                  <AddType
                    catalog={addableTypes(types, motions)}
                    stages={stages.data?.stages ?? []}
                    onAdded={(key) => {
                      void refresh();
                      setOpenKey(key);
                    }}
                  />
                ) : null}
              </div>
              {pending.length > 0 ? (
                <div className={cn("flex flex-wrap items-center gap-3", THEME_TOKENS.motion.fadeIn)}>
                  <span className={cn(THEME_TOKENS.typography.capsLabel, "hidden sm:inline")}>{copy.pendingBar}</span>
                  <Button type="button" size="sm" disabled={activating} onClick={() => void activate()}>
                    {activating ? (
                      <>
                        <VocifySpinner size={12} />
                        <span className="ml-1.5">{copy.activating}</span>
                      </>
                    ) : (
                      copy.activate
                    )}
                  </Button>
                </div>
              ) : null}
            </div>
          ) : null}
        </>
      )}
      <ConfirmAction
        open={deleteKey !== null}
        onOpenChange={(next) => {
          if (!next) setDeleteKey(null);
        }}
        title={copy.deleteTitle.replace("{name}", deleteKey ? name(deleteKey) : "")}
        description={copy.deleteConfirm}
        confirmLabel={copy.deleteAction}
        cancelLabel={t.product.cancelAction}
        tone="danger"
        pending={deleteKey !== null && busyKey === deleteKey}
        onConfirm={() => {
          if (deleteKey) void remove(deleteKey);
        }}
      />
    </div>
  );
}

/** Per open row, so the insights query only runs for the playbook on screen. */
function RowDocument({
  motionKey,
  canEdit,
  live,
  template,
  meta,
  onSaved,
  registerFlush,
  onDelete,
}: {
  motionKey: string;
  canEdit: boolean;
  live: boolean;
  template: () => EditorStep[];
  meta: React.ReactNode;
  onSaved: () => void;
  registerFlush: (flush: Flush | null) => void;
  onDelete?: () => void;
}) {
  const insights = useQuery({
    queryKey: ["playbook-insights", motionKey],
    queryFn: () => playbooksApi.insights(motionKey, "month"),
    enabled: canEdit && live,
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
      onSaved={onSaved}
      registerFlush={registerFlush}
      onDelete={onDelete}
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
