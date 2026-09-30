import { useState } from "react";
import { CompanyRow } from "@/features/playbooks/components/CompanyRow";
import { IntakePanel } from "@/features/playbooks/components/IntakePanel";
import { PlaybookRow } from "@/features/playbooks/components/PlaybookRow";
import { ProcessFooter } from "@/features/playbooks/components/ProcessFooter";
import { RuleLine } from "@/features/playbooks/components/RuleLine";
import { useIntake } from "@/features/playbooks/hooks/useIntake";
import { usePlaybookProcess } from "@/features/playbooks/hooks/usePlaybookProcess";
import { BASE_KEYS, COMPANY_ROW } from "@/features/playbooks/keys";
import { Button } from "@/components/ui/button";
import { ConfirmAction } from "@/components/ui/confirm-action";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { useLanguage } from "@/lib/i18n";
import { addableTypes, countLine, rowState, ruleNeeded } from "@/lib/playbook-doc";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card}`;

/**
 * "Vuestro proceso" (plan §14–16): one way in for the whole company, one row per call type
 * (plus "Vuestra empresa" and the reserved Interna), one action to turn changes on. This component only arranges the
 * pieces; the data and actions live in usePlaybookProcess and useIntake.
 */
export function PlaybookList() {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  const process = usePlaybookProcess();
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [browse, setBrowse] = useState(false);
  const [deleteKey, setDeleteKey] = useState<string | null>(null);
  const intake = useIntake({
    refresh: process.refresh,
    onDone: (key) => {
      setOpenKey(key);
      setBrowse(true);
    },
  });
  const { canEdit, empty, list } = process;
  const showIntake = canEdit && ((empty && !browse) || intake.open);
  const toggleOpen = (key: string) => setOpenKey((current) => (current === key ? null : key));

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

  return (
    <div className={cn(card, "px-5 md:px-7")}>
      {showIntake ? <IntakePanel intake={intake} alone={empty} name={process.name} onTemplate={() => setBrowse(true)} /> : null}

      {empty && !browse ? null : (
        <>
          {intake.found || intake.foundCompany ? (
            <div className={cn("space-y-0.5 pt-5 text-sm text-foreground", THEME_TOKENS.motion.fadeIn)} role="status">
              {intake.found ? (
                <p>{intake.found === 1 ? copy.foundOne : copy.foundMany.replace("{count}", String(intake.found))}</p>
              ) : null}
              {intake.foundCompany ? (
                <p className="text-muted-foreground">{copy.foundCompany.replace("{summary}", intake.foundCompany)}</p>
              ) : null}
            </div>
          ) : null}
          <ul className="py-1">
            <CompanyRow
              open={openKey === COMPANY_ROW}
              summary={process.companySummary}
              canEdit={canEdit}
              documentVersion={process.docVersion}
              onToggleOpen={() => toggleOpen(COMPANY_ROW)}
              onSaved={process.companySaved}
            />
            {process.rows.map((row) => {
              const state = rowState(row.status, process.details[row.key]);
              const goal = process.goalOf(row.key);
              return (
                <PlaybookRow
                  key={row.key}
                  row={row}
                  label={process.name(row.key)}
                  state={state}
                  counts={countLine(process.details[row.key], copy)}
                  open={openKey === row.key}
                  canEdit={canEdit}
                  busy={process.busyKey === row.key}
                  // The two base flows empty instead of disappearing, so an empty one has nothing to delete.
                  deletable={state !== "empty" || !BASE_KEYS.includes(row.key)}
                  documentVersion={process.docVersion}
                  template={process.template(row.key)}
                  onToggleOpen={() => toggleOpen(row.key)}
                  onSwitch={(on) => void process.toggle(row.key, on)}
                  onDelete={() => setDeleteKey(row.key)}
                  onSaved={() => void process.refresh()}
                  registerFlush={(flush) => process.registerFlush(row.key, flush)}
                  meta={
                    <>
                      {goal && copy.goals[goal] ? <p className={THEME_TOKENS.typography.capsLabel}>{copy.goals[goal]}</p> : null}
                      {state === "paused" ? <p className={THEME_TOKENS.typography.capsLabel}>{copy.pausedLine}</p> : null}
                      {canEdit && ruleNeeded(process.rows, row.key, process.routing) ? (
                        <RuleLine
                          rule={process.ruleOf(row.key)}
                          stages={process.stages}
                          onSave={(rule) => process.saveRule(row.key, rule)}
                        />
                      ) : null}
                    </>
                  }
                />
              );
            })}
            {/* Reserved type for a conversation with no customer: no playbook, never scored, nothing to switch or delete. */}
            <li className="flex items-center gap-3 border-t border-border/40 py-4 first:border-t-0">
              <span className="text-[15px] text-foreground">{t.product.interactions.internal}</span>
              <span className={cn(THEME_TOKENS.typography.capsLabel, "ml-auto")}>{copy.internalRow}</span>
            </li>
          </ul>
          {canEdit ? (
            <ProcessFooter
              showAddFromDoc={!showIntake}
              onAddFromDoc={() => intake.setOpen(true)}
              addable={addableTypes(process.types, process.motions)}
              stages={process.stages}
              showAddType={process.routing}
              onTypeAdded={(key) => {
                void process.refresh();
                setOpenKey(key);
              }}
              pendingCount={process.pending.length}
              activating={process.activating}
              onActivate={() =>
                void process.activate().then((ok) => {
                  if (ok) intake.clearFound();
                })
              }
            />
          ) : null}
        </>
      )}

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
          void process.remove(key).then((ok) => {
            if (ok && openKey === key) setOpenKey(null);
            setDeleteKey(null);
          });
        }}
      />
    </div>
  );
}
