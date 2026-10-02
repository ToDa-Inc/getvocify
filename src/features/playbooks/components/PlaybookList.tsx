import { useState } from "react";
import { CallTypePanel } from "@/features/playbooks/components/CallTypePanel";
import { CompanyKnowledge } from "@/features/playbooks/components/CompanyKnowledge";
import { IntakePanel } from "@/features/playbooks/components/IntakePanel";
import { ProcessNav, type NavItem } from "@/features/playbooks/components/ProcessNav";
import { RuleChange } from "@/features/playbooks/components/RuleChange";
import { useIntake } from "@/features/playbooks/hooks/useIntake";
import { usePlaybookProcess } from "@/features/playbooks/hooks/usePlaybookProcess";
import { BASE_KEYS, COMPANY_ROW } from "@/features/playbooks/keys";
import { Button } from "@/components/ui/button";
import { ConfirmAction } from "@/components/ui/confirm-action";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { useLanguage } from "@/lib/i18n";
import { addableTypes, publishState, publishSwitch, ruleNeeded, usedForLine } from "@/lib/playbook-doc";
import { THEME_TOKENS } from "@/lib/theme/tokens";
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
  const intake = useIntake({
    refresh: process.refresh,
    onDone: (key) => {
      if (key) setPicked(key);
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
    role: row.role && row.role !== "any" ? copy.ruleRoles[row.role] : null,
  }));
  const fallbackKey = items.find((item) => item.state !== "empty")?.key ?? items[0]?.key ?? COMPANY_ROW;
  const selected = picked === COMPANY_ROW || items.some((item) => item.key === picked) ? (picked as string) : fallbackKey;
  const row = process.rows.find((item) => item.key === selected);
  const item = items.find((entry) => entry.key === selected);

  const detail = () => {
    if (canEdit && intake.open) {
      return <IntakePanel intake={intake} alone={false} name={process.name} onTemplate={() => setBrowse(true)} />;
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
        onSaved={() => void process.refresh()}
        registerFlush={(flush) => process.registerFlush(row.key, flush)}
        meta={
          <p className={THEME_TOKENS.typography.capsLabel}>
            {line}
            {canEdit && ruleNeeded(process.rows, row.key, process.routing) ? (
              <>
                {" · "}
                <RuleChange rule={rule} stages={process.stages} onSave={(next) => process.saveRule(row.key, next)} />
              </>
            ) : null}
          </p>
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

      <div className="flex flex-col gap-4 md:flex-row md:gap-6">
        <ProcessNav
          items={items}
          selected={intake.open ? "" : selected}
          companyFilled={Boolean(process.companySummary)}
          canEdit={canEdit}
          onSelect={(key) => {
            if (intake.open) intake.close();
            intake.clearFound();
            setPicked(key);
          }}
          onImport={() => intake.setOpen(true)}
          addable={addableTypes(process.types, process.motions)}
          stages={process.stages}
          showAddType={process.routing}
          onTypeAdded={(key) => {
            void process.refresh();
            setPicked(key);
          }}
        />
        <div className="min-w-0 flex-1">{detail()}</div>
      </div>

      <ConfirmAction
        open={deleteKey !== null}
        onOpenChange={(next) => {
          if (!next) setDeleteKey(null);
        }}
        title={copy.deleteTitle.replace("{name}", deleteKey ? process.name(deleteKey) : "")}
        description={copy.deleteConfirm}
        confirmLabel={copy.deleteAction}
        cancelLabel={t.product.cancelAction}
        tone="danger"
        pending={deleteKey !== null && process.busyKey === deleteKey}
        onConfirm={() => {
          const key = deleteKey;
          if (!key) return;
          void process.remove(key).then(() => setDeleteKey(null));
        }}
      />
    </div>
  );
}
