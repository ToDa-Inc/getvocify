import { useState } from "react";
import { CallTypePanel } from "@/features/playbooks/components/CallTypePanel";
import { CompanyKnowledge } from "@/features/playbooks/components/CompanyKnowledge";
import { IntakePanel } from "@/features/playbooks/components/IntakePanel";
import { ProcessNav, type NavChannel, type NavItem } from "@/features/playbooks/components/ProcessNav";
import { AddTypeMenu } from "@/features/playbooks/components/AddTypeMenu";
import { RuleChange } from "@/features/playbooks/components/RuleChange";
import { TypeSetup } from "@/features/playbooks/components/TypeSetup";
import { useIntake } from "@/features/playbooks/hooks/useIntake";
import { usePlaybookProcess } from "@/features/playbooks/hooks/usePlaybookProcess";
import { BASE_KEYS, COMPANY_ROW } from "@/features/playbooks/keys";
import { Button } from "@/components/ui/button";
import { ConfirmAction } from "@/components/ui/confirm-action";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { useLanguage } from "@/lib/i18n";
import { addableTypes, publishState, publishSwitch, ruleNeeded, usedForLine } from "@/lib/playbook-doc";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { channelsOf, otherChannel, type LiveChannel } from "@/lib/type-channels";
import { cn } from "@/lib/utils";

const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card}`;

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
  const [picked, setPicked] = useState<string | null>(null);
  const [browse, setBrowse] = useState(false);
  const [deleteKey, setDeleteKey] = useState<string | null>(null);
  // Types by channel: the rail shows one channel at a time; until one is chosen, the one that has types.
  const [channelPick, setChannelPick] = useState<LiveChannel | null>(null);
  /** Opens a type, switching the rail to a channel it belongs to. */
  const open = (key: string, channels?: LiveChannel[]) => {
    setPicked(key);
    if (process.byChannel && key !== COMPANY_ROW) {
      const own = channels?.length ? channels : channelsOf(process.list.data, key);
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
  if (list.isLoading) {
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
  if (canEdit && empty && !browse) {
    return (
      <div className={cn(card, "px-5 md:px-7")}>
        <IntakePanel intake={intake} alone name={process.name} onTemplate={() => setBrowse(true)} />
      </div>
    );
  }

  const items: NavItem[] = process.rows.map((row) => ({
    key: row.key,
    label: process.name(row.key),
    state: publishState(row.status, process.details[row.key]),
    // Types by channel: a type has no role.
    role: !process.byChannel && row.role && row.role !== "any" ? copy.ruleRoles[row.role] : null,
  }));
  const counts = {
    call: items.filter((entry) => channelsOf(process.list.data, entry.key).includes("call")).length,
    meeting: items.filter((entry) => channelsOf(process.list.data, entry.key).includes("meeting")).length,
  };
  const channel: LiveChannel = channelPick ?? (counts.call || !counts.meeting ? "call" : "meeting");
  const shown = process.byChannel ? items.filter((entry) => channelsOf(process.list.data, entry.key).includes(channel)) : items;
  const nav: NavChannel | null = process.byChannel
    ? { value: channel, counts, onChange: (next) => { setChannelPick(next); setPicked(null); intake.close(); } }
    : null;
  const fallbackKey = shown.find((item) => item.state !== "empty")?.key ?? shown[0]?.key ?? COMPANY_ROW;
  const selected = picked === COMPANY_ROW || shown.some((item) => item.key === picked) ? (picked as string) : fallbackKey;
  const row = process.rows.find((item) => item.key === selected);
  const item = items.find((entry) => entry.key === selected);
  // Deleting from a channel on screen: a type that also serves the other channel only leaves this one.
  const leaves = (key: string) => process.byChannel && channelsOf(process.list.data, key).length > 1;
  const channelName = copy.ruleChannels[channel];

  const onTypeAdded = (key: string, label: string, channels: LiveChannel[]) => {
    if (process.byChannel) void process.typeAdded(key, label, channels);
    else void process.refresh();
    open(key, channels);
  };

  const detail = () => {
    if (canEdit && intake.open) {
      return <IntakePanel intake={intake} alone={false} name={process.name} onTemplate={() => setBrowse(true)} />;
    }
    if (process.byChannel && selected === COMPANY_ROW && picked !== COMPANY_ROW && !shown.length) {
      return (
        <div className="flex flex-col items-start gap-3 py-6">
          <p className="text-sm text-muted-foreground">{copy.channelEmpty[channel]}</p>
          {canEdit ? (
            <AddTypeMenu catalog={addableTypes(process.types, process.motions)} stages={process.stages} channel={channel} onAdded={onTypeAdded} />
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
    const line = usedForLine(row.key, rule, process.routing, process.goalOf(row.key), {
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
              channels={channelsOf(process.list.data, row.key)}
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

  return (
    <div className={cn(card, "space-y-4 p-4 md:p-6")}>
      {intake.found || intake.foundCompany ? (
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
          showAddType={process.routing || process.byChannel}
          channel={nav}
          onTypeAdded={onTypeAdded}
        />
        <div className="min-w-0 flex-1">{detail()}</div>
      </div>

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
    </div>
  );
}
