import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CallTypePanel } from "@/features/playbooks/components/CallTypePanel";
import { CompanyKnowledge } from "@/features/playbooks/components/CompanyKnowledge";
import { IntakePanel } from "@/features/playbooks/components/IntakePanel";
import { ProcessNav, type NavChannel, type NavItem } from "@/features/playbooks/components/ProcessNav";
import { AddTypeMenu } from "@/features/playbooks/components/AddTypeMenu";
import { GapAssistant } from "@/features/playbooks/components/GapAssistant";
import { ImproveHub } from "@/features/playbooks/components/ImproveHub";
import { ImproveScreen } from "@/features/playbooks/components/ImproveQueue";
import { salesProcessApi } from "@/features/sales-process/api";
import { PROCESS_QUERY } from "@/features/sales-process/useSalesProcess";
import { CompanySheet } from "@/features/playbooks/components/home/CompanySheet";
import type { HomeType } from "@/features/playbooks/components/home/FunnelBlock";
import { PlaybookHomeView } from "@/features/playbooks/components/home/PlaybookHome";
import { ProcessDialog } from "@/features/playbooks/components/home/ProcessDialog";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { playbooksApi } from "@/features/playbooks/api";
import { TrialRunner } from "@/features/playbooks/components/TrialRunner";
import { UnderstoodSummary } from "@/features/playbooks/components/UnderstoodSummary";
import { RuleChange } from "@/features/playbooks/components/RuleChange";
import { TypeSetup } from "@/features/playbooks/components/TypeSetup";
import { useIntake } from "@/features/playbooks/hooks/useIntake";
import { usePlaybookProcess } from "@/features/playbooks/hooks/usePlaybookProcess";
import { BASE_KEYS, COMPANY_ROW } from "@/features/playbooks/keys";
import { useAuth } from "@/features/auth";
import { Button } from "@/components/ui/button";
import { ConfirmAction } from "@/components/ui/confirm-action";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { useLanguage } from "@/lib/i18n";
import { companyAreaStates, splitFunnel, type CompanyOpens } from "@/lib/playbook-home";
import { addableTypes, publishState, publishSwitch, ruleNeeded, usedForLine } from "@/lib/playbook-doc";
import { viewFromParams, type ImproveView } from "@/lib/playbook-assistant";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { otherChannel, railChannels, type LiveChannel } from "@/lib/type-channels";
import { cn } from "@/lib/utils";

const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card}`;
/** The improvement views that exist today (the hub only offers these). */
const IMPROVE_VIEWS: readonly ImproveView[] = ["assistant", "trial", "improve"];

/**
 * "Vuestro proceso" (plan §14–16) as a list and a detail: on the left "Vuestra empresa" and
 * one entry per call type, on the right the one that is open, in tabs. Nothing grows the page:
 * choosing is one click, and each playbook's layers are tabs instead of one long scroll. One
 * way in for the whole company (the intake box); each call type publishes its own changes. This
 * component only arranges the pieces; the data and actions live in usePlaybookProcess and
 * useIntake.
 */
export function PlaybookList() {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const process = usePlaybookProcess();
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const [picked, setPicked] = useState<string | null>(null);
  const [browse, setBrowse] = useState(false);
  const [deleteKey, setDeleteKey] = useState<string | null>(null);
  // Types by channel: the rail shows one channel at a time; until one is chosen, the one that has types.
  const [channelPick, setChannelPick] = useState<LiveChannel | null>(null);
  /** Opens a type, switching the rail to a channel it belongs to. */
  const open = (key: string, channels?: LiveChannel[]) => {
    setPicked(key);
    if (key !== COMPANY_ROW) {
      const own = channels?.length ? channels : railChannels(process.list.data, key);
      setChannelPick((current) => (current && own.includes(current) ? current : own[0]));
    }
  };
  const intake = useIntake({
    refresh: process.refresh,
    onDone: (key) => {
      if (key) open(key);
      setBrowse(true);
    },
  });
  const { canEdit, empty, list } = process;
  // The playbook assistant (guided questions, trial, improvements) is on per company and only for owner and admin.
  const assistantOn = canEdit && (user?.company?.features ?? []).includes("PLAYBOOK_ASSISTANT_ENABLED");
  const asked = viewFromParams(params);
  const view = assistantOn && asked && IMPROVE_VIEWS.includes(asked) ? asked : null;
  // The company's own sales process: its types in order, with no Llamadas / Reuniones split (spec 2026-10-17).
  const processOn = canEdit && (user?.company?.features ?? []).includes("SALES_PROCESS_ENABLED");
  const processQuery = useQuery({ queryKey: PROCESS_QUERY, queryFn: salesProcessApi.get, enabled: processOn, retry: false, staleTime: 30_000 });
  const processTypes = processQuery.data?.types ?? null;
  // The Playbook as one screen (sales funnel, company, other calls): everything is created and edited in windows over it.
  const [dialog, setDialog] = useState<"funnel" | "other" | null>(null);
  const [typeSheet, setTypeSheet] = useState<string | null>(null);
  const [companyOpen, setCompanyOpen] = useState<CompanyOpens | null>(null);
  const queryClient = useQueryClient();
  const companyQuery = useQuery({ queryKey: ["playbook-company"], queryFn: playbooksApi.company, enabled: processOn, retry: false, staleTime: 30_000 });
  const setView = (next: ImproveView | null) =>
    setParams((previous) => {
      const search = new URLSearchParams(previous);
      if (next) search.set("view", next);
      else search.delete("view");
      return search;
    });
  /** Back to the playbook: what the assistant changed is read again. */
  const closeView = () => {
    setView(null);
    void process.refresh();
    process.reloadDocuments();
  };

  if (list.isError) {
    return (
      <div className={cn(card, "flex items-center gap-3 p-6")} role="alert">
        <p className="text-sm text-muted-foreground">{t.product.playbookEditorLoadFailed}</p>
        <Button type="button" variant="outline" size="sm" onClick={() => void list.refetch()}>
          {t.product.retry}
        </Button>
      </div>
    );
  }
  if (list.isLoading || (processOn && processQuery.isLoading)) {
    return (
      <div className={cn(card, "p-6")}>
        <p className="inline-flex items-center gap-2 text-sm text-muted-foreground" role="status">
          <VocifySpinner size={12} />
          {t.product.playbookEditorLoading}
        </p>
      </div>
    );
  }

  // First time: the intake box is the whole section. One paste fills everything.
  if (canEdit && empty && !browse && !processOn) {
    return (
      <IntakePanel intake={intake} alone name={process.name} onTemplate={() => setBrowse(true)} assistant={assistantOn} />
    );
  }

  // The company's own order, when it has defined its process; otherwise the order the list always had.
  const placed = new Map((processTypes ?? []).map((entry) => [entry.key, entry.position]));
  const orderedRows = processOn && processTypes?.length ? process.rows.filter((row) => placed.has(row.key)).sort((a, b) => (placed.get(a.key) ?? 999) - (placed.get(b.key) ?? 999)) : process.rows;
  const items: NavItem[] = orderedRows.map((row) => ({
    key: row.key,
    label: process.name(row.key),
    state: publishState(row.status, process.details[row.key]),
    // Types by channel: a type has no role.
    role: !process.byChannel && row.role && row.role !== "any" ? copy.ruleRoles[row.role] : null,
  }));
  const counts = {
    call: items.filter((entry) => railChannels(process.list.data, entry.key).includes("call")).length,
    meeting: items.filter((entry) => railChannels(process.list.data, entry.key).includes("meeting")).length,
  };
  const channel: LiveChannel = channelPick ?? (counts.call || !counts.meeting ? "call" : "meeting");
  // With the editable process there are no channels: one list of the company's types, in its order.
  const shown = processOn ? items : items.filter((entry) => railChannels(process.list.data, entry.key).includes(channel));
  const nav: NavChannel | null = processOn ? null : { value: channel, counts, onChange: (next) => { setChannelPick(next); setPicked(null); intake.close(); } };
  const fallbackKey = shown.find((item) => item.state !== "empty")?.key ?? shown[0]?.key ?? COMPANY_ROW;
  const selected = picked === COMPANY_ROW || shown.some((item) => item.key === picked) ? (picked as string) : fallbackKey;
  const row = process.rows.find((item) => item.key === selected);
  const item = items.find((entry) => entry.key === selected);
  // Deleting from a channel on screen: a type that also serves the other channel only leaves this one.
  const leaves = (key: string) => !processOn && railChannels(process.list.data, key).length > 1;
  const channelName = copy.ruleChannels[channel];

  const onTypeAdded = (key: string, label: string, channels: LiveChannel[]) => {
    if (process.byChannel) void process.typeAdded(key, label, channels);
    else void process.refresh();
    open(key, channels);
  };

  const detail = () => {
    if (canEdit && intake.open) {
      return <IntakePanel intake={intake} alone={false} name={process.name} onTemplate={() => setBrowse(true)} assistant={assistantOn} />;
    }
    if (selected === COMPANY_ROW && picked !== COMPANY_ROW && !shown.length) {
      return (
        <div className="flex flex-col items-start gap-3 py-6">
          <p className="text-sm text-muted-foreground">{copy.channelEmpty[channel]}</p>
          {canEdit ? (
            <AddTypeMenu catalog={addableTypes(process.types, process.motions)} stages={process.stages} channel={channel} byChannel={process.byChannel} onAdded={onTypeAdded} />
          ) : null}
        </div>
      );
    }
    if (selected === COMPANY_ROW || !row || !item) {
      return (
        <CompanyKnowledge
          key={process.docVersion}
          canEdit={canEdit}
          onSaved={process.companySaved}
        />
      );
    }
    const rule = process.ruleOf(row.key);
    // Where it is used, without the "success = …" goal: a thing the rep cannot act on and the admin does not need here.
    const line = usedForLine(row.key, rule, process.routing, null, {
      ...copy,
      roles: copy.ruleRoles,
      channels: copy.ruleChannels,
      contacts: copy.ruleContacts,
      stages: copy.ruleStages,
      join: copy.ruleJoin,
    });
    return (
      <CallTypePanel
        key={`${row.key}:${process.docVersion}`}
        row={row}
        label={item.label}
        role={item.role}
        state={item.state}
        switchOn={publishSwitch(row.status, process.details[row.key])}
        canEdit={canEdit}
        busy={process.busyKey === row.key}
        // The two base flows empty instead of disappearing, so an empty one has nothing to delete.
        deletable={item.state !== "empty" || !BASE_KEYS.includes(row.key)}
        template={process.template(row.key)}
        onPublish={() => void process.publish(row.key)}
        onSwitch={(on) => void process.toggle(row.key, on)}
        onDelete={() => setDeleteKey(row.key)}
        deleteLabel={leaves(row.key) ? copy.leaveChannel.replace("{channel}", channelName) : undefined}
        onSaved={() => void process.refresh()}
        registerFlush={(flush) => process.registerFlush(row.key, flush)}
        meta={
          process.byChannel ? (
            <TypeSetup
              channels={railChannels(process.list.data, row.key)}
              recognize={process.details[row.key]?.recognize ?? null}
              stats={process.stats[row.key] ?? null}
              rule={rule}
              stages={process.stages}
              canEdit={canEdit}
              onEdit={(edit) => process.editType(row.key, edit)}
              onSaveRule={(next) => process.saveRule(row.key, next)}
            />
          ) : (
          <p className={THEME_TOKENS.typography.capsLabel}>
            {line}
            {canEdit && ruleNeeded(process.rows, row.key, process.routing) ? (
              <>
                {" · "}
                <RuleChange rule={rule} stages={process.stages} onSave={(next) => process.saveRule(row.key, next)} />
              </>
            ) : null}
          </p>
          )
        }
      />
    );
  };

  const confirmDelete = (
    <ConfirmAction
      open={deleteKey !== null}
      onOpenChange={(next) => {
        if (!next) setDeleteKey(null);
      }}
      title={(deleteKey && leaves(deleteKey) ? copy.leaveChannelTitle.replace("{channel}", channelName) : copy.deleteTitle).replace(
        "{name}",
        deleteKey ? process.name(deleteKey) : "",
      )}
      description={
        deleteKey && leaves(deleteKey)
          ? copy.leaveChannelConfirm.replace("{other}", copy.ruleChannels[otherChannel(channel)])
          : copy.deleteConfirm
      }
      confirmLabel={deleteKey && leaves(deleteKey) ? copy.leaveChannelAction : copy.deleteAction}
      cancelLabel={t.product.cancelAction}
      tone="danger"
      pending={deleteKey !== null && process.busyKey === deleteKey}
      onConfirm={() => {
        const key = deleteKey;
        if (!key) return;
        const done = leaves(key) ? process.leaveChannel(key, channel) : process.remove(key);
        void done.then(() => setDeleteKey(null));
      }}
    />
  );

  const understood = assistantOn && intake.understood ? intake.understood : null;
  const playbook = (
    <div className={cn(card, "space-y-4 p-4 md:p-6")}>
      {understood ? (
        <UnderstoodSummary
          summary={understood.summary}
          failed={understood.failed}
          conflicts={understood.conflicts}
          readError={(code) => (code && copy.readErrors[code]) || ""}
          onNext={() => {
            intake.clearUnderstood();
            setView("assistant");
          }}
          onLater={intake.clearUnderstood}
        />
      ) : null}
      {!understood && (intake.found || intake.foundCompany) ? (
        <div className={cn("space-y-0.5 bg-beige/10 px-4 py-2.5 text-sm text-foreground", THEME_TOKENS.radius.control, THEME_TOKENS.motion.fadeIn)} role="status">
          {intake.found ? <p>{intake.found === 1 ? copy.foundOne : copy.foundMany.replace("{count}", String(intake.found))}</p> : null}
          {intake.foundCompany ? (
            <p className="text-muted-foreground">{copy.foundCompany.replace("{summary}", intake.foundCompany)}</p>
          ) : null}
        </div>
      ) : null}

      {process.byChannel && process.detection ? (
        <p className={cn("text-[13px]", process.detection.by_channel ? "text-muted-foreground" : "text-destructive")} role="status">
          {process.detection.by_channel ? copy.detectionOn : copy.detectionOff}
        </p>
      ) : null}

      <div className="flex flex-col gap-4 md:flex-row md:gap-6">
        <ProcessNav
          items={shown}
          selected={intake.open ? "" : selected}
          companyFilled={Boolean(process.companySummary)}
          canEdit={canEdit}
          onSelect={(key) => {
            if (intake.open) intake.close();
            intake.clearFound();
            open(key);
          }}
          onImport={() => intake.setOpen(true)}
          addable={addableTypes(process.types, process.motions)}
          stages={process.stages}
          showAddType={!processOn}
          channel={nav}
          byChannel={process.byChannel}
          onTypeAdded={onTypeAdded}
        />
        <div className="min-w-0 flex-1">{detail()}</div>
      </div>

      {confirmDelete}
    </div>
  );

  const homeTypes: HomeType[] = (processTypes ?? []).map((entry) => ({
    key: entry.key,
    label: entry.label,
    goal: entry.goal ?? null,
    description: entry.recognize ?? null,
    stage: entry.stage,
    state: items.find((item) => item.key === entry.key)?.state ?? "empty",
  }));
  const { funnel: funnelTypes, other: otherTypes } = splitFunnel(homeTypes);
  const homeScreen = (
    <>
      <PlaybookHomeView
        types={homeTypes}
        areas={companyAreaStates(companyQuery.data?.knowledge, user?.productContext)}
        canEdit={canEdit}
        onCreateFunnel={() => setDialog("funnel")}
        onOpenType={(key) => {
          open(key);
          setTypeSheet(key);
        }}
        onCreateCompany={() => setCompanyOpen("notes")}
        onOpenCompany={setCompanyOpen}
        onCreateOther={() => setDialog("other")}
      />
      <ProcessDialog
        open={dialog !== null}
        onOpenChange={(next) => !next && setDialog(null)}
        kind={dialog ?? "funnel"}
        first={(dialog === "other" ? otherTypes : funnelTypes).length === 0}
        intake={intake}
        assistantOn={assistantOn}
        firstEmptyKey={funnelTypes.find((entry) => entry.state === "empty")?.key ?? null}
        name={process.name}
        onChanged={() => {
          void queryClient.invalidateQueries({ queryKey: PROCESS_QUERY });
          void process.refresh();
        }}
        onOpenType={(key) => {
          open(key);
          setTypeSheet(key);
        }}
      />
      <Sheet open={typeSheet !== null} onOpenChange={(next) => !next && setTypeSheet(null)}>
        <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-3xl">
          <SheetTitle className="sr-only">{typeSheet ? process.name(typeSheet) : ""}</SheetTitle>
          <SheetDescription className="sr-only">{copy.sectionTitle}</SheetDescription>
          <div className="pt-6">{typeSheet ? detail() : null}</div>
        </SheetContent>
      </Sheet>
      <CompanySheet
        open={companyOpen !== null}
        onOpenChange={(next) => {
          if (!next) {
            setCompanyOpen(null);
            void queryClient.invalidateQueries({ queryKey: ["playbook-company"] });
          }
        }}
        opens={companyOpen ?? "notes"}
        canEdit={canEdit}
        onSaved={() => void process.companySaved()}
      />
      {confirmDelete}
    </>
  );
  const body = processOn ? homeScreen : playbook;
  if (!assistantOn) return body;
  return (
    <div className="space-y-4">
      <ImproveHub view={view} views={IMPROVE_VIEWS} onView={(next) => (next ? setView(next) : closeView())} />
      {view === "assistant" ? (
        <GapAssistant
          motionKey={selected === COMPANY_ROW ? null : selected}
          onChanged={() => void process.refresh()}
          onTry={() => setView("trial")}
          onBack={closeView}
        />
      ) : view === "trial" ? (
        <TrialRunner motionKey={selected === COMPANY_ROW ? null : selected} onChanged={() => void process.refresh()} onBack={closeView} />
      ) : view === "improve" ? (
        <ImproveScreen typeName={(key) => (key ? process.name(key) : "")} onChanged={() => void process.refresh()} />
      ) : (
        body
      )}
    </div>
  );
}
