import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Check, Sparkles, Trash2, Upload, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmAction } from "@/components/ui/confirm-action";
import { Skeleton } from "@/components/ui/skeleton";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { GapAssistant } from "@/features/playbooks/components/GapAssistant";
import type { HomeType } from "@/features/playbooks/components/home/FunnelBlock";
import { StepLine, WindowShell } from "@/features/playbooks/components/home/WindowShell";
import { PlaybookStart, type SourceInput } from "@/features/playbooks/components/PlaybookStart";
import type { Intake } from "@/features/playbooks/hooks/useIntake";
import { saveTypeContent } from "@/features/playbooks/typeContent";
import { useSalesProcess } from "@/features/sales-process/useSalesProcess";
import { withFunnelStages } from "@/lib/company-areas";
import { useLanguage } from "@/lib/i18n";
import { rowProblem, scopeProblem, type DraftType } from "@/lib/sales-process";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

type Step = "define" | "content" | "ask" | "done";
const plain = "block w-full bg-transparent text-foreground placeholder:text-muted-foreground/50 focus:outline-none disabled:opacity-60";

/**
 * Create or edit the sales process (or the calls outside it) in one window, screen after screen:
 *   1. the interactions, in order: name and goal (a call outside the funnel only needs a name);
 *   2. their content: one document for all of them, or a document or a pasted text for each; or Vocify asks and builds it;
 *   3. done.
 * The stage of each interaction (first contact or deal) follows from its place, so it is never asked.
 */
export function FunnelWindow({
  open,
  onOpenChange,
  kind,
  types,
  intake,
  assistantOn,
  onChanged,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  kind: "funnel" | "other";
  /** The company's interactions as the page shows them (with whether each already has content). */
  types: HomeType[];
  intake: Intake;
  assistantOn: boolean;
  onChanged: () => void;
}) {
  const { t } = useLanguage();
  const c = t.product.pb2.home;
  const funnel = kind === "funnel";
  const process = useSalesProcess({ scope: kind });
  const [step, setStep] = useState<Step>("define");
  const [confirm, setConfirm] = useState(false);
  const [writing, setWriting] = useState<string | "whole" | null>(null);
  // After a "Siguiente" that could not go on, each row says what it is missing, as it is typed.
  const [tried, setTried] = useState(false);
  const listRef = useRef<HTMLOListElement>(null);
  const seeded = useRef(false);

  // Every opening starts from what is saved, on the first screen.
  useEffect(() => {
    if (!open) return;
    process.reset();
    seeded.current = false;
    setStep("define");
    setWriting(null);
    setTried(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const blank = (): DraftType => ({ label: "", stage: funnel ? "deal" : "other" });
  const rows = process.list;
  const setRows = (next: DraftType[]) => process.setList(funnel ? withFunnelStages(next) : next);
  // Nothing defined yet: one empty row to type into, never an empty list with a disabled button.
  useEffect(() => {
    if (open && process.status === "ready" && !seeded.current && process.saved !== null) {
      seeded.current = true;
      if (!rows.length) setRows([blank()]);
    }
  });

  const update = (index: number, patch: Partial<DraftType>) => setRows(rows.map((row, at) => (at === index ? { ...row, ...patch } : row)));
  const example = () => {
    const names = c.exampleNames.split("|");
    const goals = c.exampleGoals.split("|");
    setRows(names.map((label, i) => ({ label, goal: goals[i], stage: "deal" })));
  };
  const issue = (row: DraftType) => (tried ? rowProblem(row, process.all) : null);
  const tryNext = () => {
    if (scopeProblem(rows, process.all)) {
      setTried(true);
      requestAnimationFrame(() => listRef.current?.querySelector<HTMLInputElement>('[aria-invalid="true"]')?.focus());
      return;
    }
    if (process.removing.length) setConfirm(true);
    else void next();
  };
  const next = async () => {
    if (await process.save()) {
      onChanged();
      setStep("content");
    }
  };

  // The interactions of this window as saved, with whether each already has content.
  const saved = (process.saved ?? []).filter((item) => (item.stage === "other") === !funnel);
  const state = (key: string) => types.find((item) => item.key === key)?.state ?? "empty";
  const written = saved.filter((item) => state(item.key) !== "empty").length;
  const close = () => onOpenChange(false);

  const title = step === "define" ? (funnel ? c.processDialogTitle : c.otherDialogTitle) : step === "content" ? c.contentTitle : step === "ask" ? c.pathAsk : funnel ? c.doneTitle : c.otherDoneTitle;
  const lead = step === "define" ? (funnel ? c.funnelWindowLead : c.otherWindowLead) : step === "content" ? c.contentLead : undefined;

  const footer =
    step === "define" ? (
      <>
        <StepLine steps={[funnel ? c.stepSteps : c.stepInteractions, c.stepContent]} at={0} />
        <Button type="button" disabled={process.saving || process.status !== "ready"} onClick={tryNext}>
          {process.saving ? <VocifySpinner size={12} tone="onFill" /> : null}
          {c.next}
        </Button>
      </>
    ) : step === "content" ? (
      <>
        <Button type="button" variant="quiet" size="text" onClick={() => setStep("define")}>
          <ArrowLeft aria-hidden strokeWidth={1.5} />
          {c.backStep}
        </Button>
        <Button type="button" onClick={() => setStep("done")}>
          {c.finish}
        </Button>
      </>
    ) : step === "ask" ? (
      <>
        <Button type="button" variant="quiet" size="text" onClick={() => setStep("content")}>
          <ArrowLeft aria-hidden strokeWidth={1.5} />
          {c.backStep}
        </Button>
        <Button type="button" onClick={() => setStep("done")}>
          {c.finish}
        </Button>
      </>
    ) : (
      <>
        <span />
        <Button type="button" onClick={close}>
          {c.close}
        </Button>
      </>
    );

  let body;
  if (step === "define") {
    body =
      process.status === "loading" ? (
        <div className="space-y-4" role="status" aria-busy="true">
          <Skeleton className="h-16 w-full motion-reduce:animate-none" />
          <Skeleton className="h-16 w-full motion-reduce:animate-none" />
        </div>
      ) : process.status === "not_activated" ? (
        <p className={THEME_TOKENS.typography.body}>{t.product.pb2.process.errors.not_activated}</p>
      ) : (
        <div className="space-y-5">
          {funnel && rows.length === 1 && !rows[0].label && !rows[0].key ? (
            <button type="button" onClick={example} className="text-[13px] text-muted-foreground underline-offset-4 hover:text-foreground hover:underline">
              {c.example}
            </button>
          ) : null}
          <ol ref={listRef} className="space-y-5">
            {rows.map((row, index) => {
              const problem = issue(row);
              return (
              <li key={row.key ?? `new-${index}`} className="grid grid-cols-[1.75rem_1fr_auto] items-start gap-x-3 border-b border-border/50 pb-5">
                <span className="mt-1 flex h-6 w-6 items-center justify-center rounded-full bg-secondary text-xs tabular-nums text-muted-foreground" aria-hidden>
                  {index + 1}
                </span>
                <div className="min-w-0 space-y-2">
                  <input
                    autoFocus={index === rows.length - 1 && !row.label}
                    value={row.label}
                    maxLength={60}
                    disabled={process.saving}
                    onChange={(event) => update(index, { label: event.target.value })}
                    placeholder={funnel ? c.namePh : c.otherNamePh}
                    aria-label={funnel ? c.namePh : c.otherNamePh}
                    aria-invalid={problem === "empty_name" || problem === "duplicate_name"}
                    className={cn(plain, "text-[17px] font-medium")}
                  />
                  {funnel ? (
                    <label className="block space-y-0.5 pt-1">
                      <span className={THEME_TOKENS.typography.fieldLabel}>
                        {c.goalLabel}{" "}
                        <span className="font-normal text-muted-foreground/70">
                          {index === rows.length - 1 ? c.goalToClose : c.goalToNext.replace("{next}", rows[index + 1].label.trim() || c.nextFallback)}
                        </span>
                      </span>
                    <input
                      value={row.goal ?? ""}
                      maxLength={160}
                      disabled={process.saving}
                      onChange={(event) => update(index, { goal: event.target.value })}
                      placeholder={c.goalPh}
                      aria-invalid={problem === "goal_required"}
                      className={cn(plain, "text-[14px] text-foreground/80")}
                    />
                    </label>
                  ) : null}
                  {problem ? (
                    <p className="text-[13px] text-destructive" role="alert">
                      {problem === "goal_required" ? c.rowNeedsGoal : problem === "duplicate_name" ? c.rowNameTaken : c.rowNeedsName}
                    </p>
                  ) : null}
                </div>
                {rows.length > 1 ? (
                  <button
                    type="button"
                    aria-label={c.remove}
                    disabled={process.saving}
                    onClick={() => setRows(rows.filter((_, at) => at !== index))}
                    className="mt-1 rounded-md p-1 text-muted-foreground hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <Trash2 aria-hidden className="h-4 w-4" strokeWidth={1.5} />
                  </button>
                ) : (
                  <span />
                )}
              </li>
              );
            })}
          </ol>
          <Button type="button" variant="quiet" size="text" disabled={process.saving || rows.length >= 20} onClick={() => setRows([...rows, blank()])}>
            <Plus aria-hidden strokeWidth={1.5} />
            {funnel ? c.addStep : c.addInteraction}
          </Button>
          {process.problem ? (
            <p className="text-sm text-destructive" role="alert">
              {t.product.pb2.process.errors[process.problem] ?? t.product.pb2.process.errors.unknown}
            </p>
          ) : null}
        </div>
      );
  } else if (step === "content") {
    const contentBox = (key: string | "whole") => (
      <PlaybookStart
        minHeight="min-h-[120px]"
        placeholder={key === "whole" ? c.wholePh : c.contentPh}
        readingLabel={c.reading}
        submitLabel={c.save}
        onCancel={() => setWriting(null)}
        submit={async (source: SourceInput) => {
          if (key === "whole") await intake.submit(source);
          else await saveTypeContent(key, source);
          setWriting(null);
          onChanged();
        }}
      />
    );
    body = (
      <div className="space-y-5">
        {funnel ? (
          writing === "whole" ? (
            <div className={THEME_TOKENS.motion.fadeIn}>{contentBox("whole")}</div>
          ) : (
            <button
              type="button"
              onClick={() => setWriting("whole")}
              className={cn(THEME_TOKENS.radius.control, "flex w-full items-center gap-3 border border-dashed border-border px-4 py-3 text-left transition-colors hover:border-beige/40 hover:bg-secondary/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring")}
            >
              <Upload aria-hidden className="h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.5} />
              <span className="text-[14px] text-foreground">
                {c.wholeBar} <span className="text-muted-foreground">{c.wholeBarHint}</span>
              </span>
            </button>
          )
        ) : null}
        {intake.notice && writing === null ? <p className="text-sm text-destructive" role="alert">{intake.notice}</p> : null}
        <ul className="divide-y divide-border/50">
          {saved.map((item, index) => (
            <li key={item.key} className="space-y-3 py-4">
              <div className="flex items-center gap-3">
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-secondary text-xs tabular-nums text-muted-foreground" aria-hidden>
                  {index + 1}
                </span>
                <span className="min-w-0 flex-1 truncate text-[15px] font-medium text-foreground">{item.label}</span>
                {state(item.key) !== "empty" ? (
                  <span className="inline-flex items-center gap-1 text-[13px] text-success">
                    <Check aria-hidden className="h-3.5 w-3.5" strokeWidth={2} />
                    {c.ready}
                  </span>
                ) : writing !== item.key ? (
                  <Button type="button" variant="outline" size="sm" onClick={() => setWriting(item.key)}>
                    {c.addContent}
                  </Button>
                ) : null}
              </div>
              {writing === item.key ? <div className={THEME_TOKENS.motion.fadeIn}>{contentBox(item.key)}</div> : null}
            </li>
          ))}
        </ul>
        {assistantOn && funnel ? (
          <button type="button" onClick={() => setStep("ask")} className="inline-flex items-center gap-2 text-[13px] text-muted-foreground hover:text-foreground">
            <Sparkles aria-hidden className="h-4 w-4" strokeWidth={1.5} />
            {c.askLink}
          </button>
        ) : null}
      </div>
    );
  } else if (step === "ask") {
    body = <GapAssistant motionKey={null} onChanged={onChanged} onTry={() => setStep("done")} onBack={() => setStep("content")} />;
  } else {
    body = (
      <div className="space-y-3 py-6 text-center">
        <span className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-success/10 text-success">
          <Check aria-hidden className="h-5 w-5" strokeWidth={1.75} />
        </span>
        <p className="text-[15px] text-muted-foreground">{c.doneLead.replace("{done}", String(written)).replace("{total}", String(saved.length))}</p>
      </div>
    );
  }

  return (
    <>
      <WindowShell open={open} onOpenChange={onOpenChange} title={title} lead={lead} footer={footer}>
        {body}
      </WindowShell>
      <ConfirmAction
        open={confirm}
        onOpenChange={setConfirm}
        title={t.product.pb2.process.removeTitle.replace("{names}", process.removing.join(", "))}
        description={t.product.pb2.process.removeConfirm}
        confirmLabel={t.product.pb2.process.removeAction}
        cancelLabel={t.product.cancelAction}
        tone="danger"
        pending={process.saving}
        onConfirm={() => void next().then(() => setConfirm(false))}
      />
    </>
  );
}
