import { useEffect, useState } from "react";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import type { Trial, TrialRun } from "@/features/playbooks/assistantApi";
import { AnswerBox } from "@/features/playbooks/components/AnswerBox";
import { QuoteBubble } from "@/features/playbooks/components/Bubbles";
import { CaseCard, RunBubble } from "@/features/playbooks/components/CaseCard";
import { SegmentMeter, type SegmentTone } from "@/features/playbooks/components/SegmentMeter";
import { TrialResultView } from "@/features/playbooks/components/TrialResult";
import { useTrial, type TrialPhase } from "@/features/playbooks/hooks/useTrial";
import { useLanguage } from "@/lib/i18n";
import { topicLabel, trialMeter } from "@/lib/playbook-assistant";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card}`;
const MARK_TONE: Record<string, SegmentTone> = { approved: "success", corrected: "warning", unknown: "muted", pending: "pending" };

export type TrialRunnerViewProps = {
  status: "loading" | "ready" | "error" | "not_activated";
  trial: Trial | null;
  caseId: string | null;
  run: TrialRun | null;
  phase: TrialPhase;
  deciding: boolean;
  /** The code of what went wrong, for the screen to word. */
  problem: string | null;
  value: string;
  onValue: (value: string) => void;
  onApprove: () => void;
  onUnknown: () => void;
  onWrite: (mode: "say" | "never") => void;
  onSubmitWriting: (text: string) => void;
  onCancelWriting: () => void;
  onOwn: () => void;
  onSimilarSame: () => void;
  onSimilarOther: () => void;
  onFinish: () => void;
  onRetry: () => void;
};

function Key({ children }: { children: string }) {
  return (
    <span aria-hidden className="hidden rounded border border-current/25 px-1 text-[11px] leading-4 opacity-70 md:inline">
      {children}
    </span>
  );
}

/**
 * "La prueba", one case at a time: what the customer says, what live help would show a rep (the real thing, made
 * with the draft) and four ways to answer: Vale, Yo diría…, No lo sé, Nunca digas esto. After a correction the case
 * runs again and one similar phrase is checked, so the Head of Sales sees whether the answer holds.
 */
export function TrialRunnerView(props: TrialRunnerViewProps) {
  const { status, trial, caseId, run, phase, deciding, problem, value, onValue } = props;
  const { t } = useLanguage();
  const c = t.product.pb2.improve;
  const current = trial?.cases.find((item) => item.id === caseId) ?? null;
  const message = problem ? (phase.kind === "writing" && phase.mode === "branch" && problem === "guidance_too_long" ? c.tooLongBranch : (c.errors[problem] ?? c.errors.unknown)) : null;

  const header = (
    <header className="flex flex-wrap items-end justify-between gap-3">
      <div className="space-y-0.5">
        <h2 className={THEME_TOKENS.typography.panelTitle}>{c.trialTitle}</h2>
        <p className="max-w-md text-[13px] leading-snug text-muted-foreground">{c.trialLead}</p>
      </div>
      {trial && status === "ready" ? (
        <div className="flex items-center gap-3">
          <SegmentMeter
            className="w-28"
            segments={trialMeter(trial.cases.map((item) => item.verdict ?? "").filter(Boolean), trial.total).map((mark) => MARK_TONE[mark])}
            label={`${trial.decided} ${c.of} ${trial.total}`}
          />
          <span className="text-xs tabular-nums text-muted-foreground">
            {Math.min(trial.decided + 1, trial.total)} {c.of} {trial.total}
          </span>
          {trial.decided >= 3 ? (
            <Button type="button" variant="quiet" size="text" onClick={props.onFinish}>
              {c.finish}
            </Button>
          ) : null}
        </div>
      ) : null}
    </header>
  );

  let body;
  if (status === "loading") {
    body = (
      <div className={cn(card, "space-y-3 p-6")} role="status" aria-busy="true">
        <Skeleton className="h-3 w-1/3 motion-reduce:animate-none" />
        <Skeleton className="h-14 w-full motion-reduce:animate-none" />
        <Skeleton className="h-14 w-full motion-reduce:animate-none" />
        <span className="sr-only">{c.assistantLoading}</span>
      </div>
    );
  } else if (status === "not_activated") {
    body = <p className={cn(card, "p-5", THEME_TOKENS.typography.body)}>{c.notActivated}</p>;
  } else if (status === "error" || !trial) {
    body = (
      <div className={cn(card, "flex flex-wrap items-center gap-3 p-5")} role="alert">
        <p className={THEME_TOKENS.typography.body}>{c.loadFailed}</p>
        <Button type="button" variant="outline" size="sm" onClick={props.onRetry}>
          {c.retry}
        </Button>
      </div>
    );
  } else if (!trial.total) {
    body = <p className={cn(card, "p-5", THEME_TOKENS.typography.body)}>{c.trialEmpty}</p>;
  } else if (!current) {
    body = null;
  } else if (phase.kind === "after") {
    const similar = phase.similar;
    body = (
      <div className="space-y-4">
        <CaseCard source={current.source} clientText={current.client_text} run={phase.run} cardLabel={c.nowAnswers}>
          <p className="flex items-center gap-1.5 px-1 text-xs text-success">
            <Check aria-hidden className="h-3.5 w-3.5" strokeWidth={2} />
            {c.savedTitle}
          </p>
        </CaseCard>
        {similar ? (
          <section className={cn(card, "space-y-4 p-5 md:p-6", THEME_TOKENS.motion.fadeIn)} aria-labelledby="trial-similar">
            <h3 id="trial-similar" className={THEME_TOKENS.typography.groupTitle}>
              {c.similarTitle}
            </h3>
            <QuoteBubble>{similar.text}</QuoteBubble>
            <RunBubble run={similar.run} label={c.nowAnswers} />
            <div className="flex flex-wrap items-center gap-2">
              <Button type="button" onClick={props.onSimilarSame}>
                {c.similarSame}
              </Button>
              <Button type="button" variant="outline" onClick={props.onSimilarOther}>
                {c.similarOther}
              </Button>
            </div>
          </section>
        ) : (
          <Button type="button" onClick={props.onSimilarSame}>
            {trial.current_id ? c.next : c.finish}
          </Button>
        )}
      </div>
    );
  } else if (phase.kind === "writing") {
    const mode = phase.mode;
    body = (
      <CaseCard source={current.source} clientText={current.client_text} run={run} className="space-y-4">
        <h3 className="text-[19px] font-medium leading-snug tracking-tight text-foreground">
          {mode === "never" ? c.neverHeading : mode === "branch" ? c.branchHeading : c.sayHeading}
        </h3>
        {mode === "branch" && phase.situation ? <QuoteBubble>{phase.situation}</QuoteBubble> : null}
        <AnswerBox
          value={value}
          onChange={onValue}
          onSubmit={(source) => props.onSubmitWriting(source.payload)}
          busy={deciding}
          allowFile={false}
          focusKey={`${phase.caseId}:${mode}`}
          copy={{
            placeholder: mode === "never" ? c.neverPlaceholder : c.sayPlaceholder,
            submit: c.answerSave,
            attach: c.fileAttach,
            removeFile: c.fileRemove,
            unsupported: c.fileUnsupported,
            hint: c.answerHint,
          }}
          footer={
            <Button type="button" variant="quiet" size="text" disabled={deciding} onClick={props.onCancelWriting}>
              {c.cancel}
            </Button>
          }
        />
        {deciding ? (
          <p className="inline-flex items-center gap-2 px-1 text-sm text-muted-foreground" role="status">
            <VocifySpinner size={12} />
            {c.answerSaving}
          </p>
        ) : null}
        {message ? (
          <div className="space-y-2" role="alert">
            <p className="px-1 text-sm text-destructive">{message}</p>
            {mode === "branch" && problem === "guidance_too_long" ? (
              <Button type="button" variant="outline" size="sm" disabled={deciding || !value.trim()} onClick={props.onOwn}>
                {c.saveOwn}
              </Button>
            ) : null}
          </div>
        ) : null}
      </CaseCard>
    );
  } else {
    const canApprove = Boolean(run?.card);
    const canNever = Boolean(run?.card?.source_id);
    const busy = deciding || !run;
    body = (
      <CaseCard source={current.source} clientText={current.client_text} run={run}>
        <div className="flex flex-wrap items-center gap-2">
          {canApprove ? (
            <Button type="button" disabled={busy} onClick={props.onApprove}>
              {run?.grounded && run.card?.source_id ? c.actionOk : c.actionAdopt}
              <Key>1</Key>
            </Button>
          ) : null}
          <Button type="button" variant={canApprove ? "outline" : "default"} disabled={busy} onClick={() => props.onWrite("say")}>
            {c.actionSay}
            <Key>2</Key>
          </Button>
          <Button type="button" variant="quiet" size="text" disabled={busy} onClick={props.onUnknown}>
            {canApprove ? c.actionUnknown : c.actionSkip}
            <Key>3</Key>
          </Button>
          {canNever ? (
            <Button type="button" variant="dangerGhost" size="text" disabled={busy} onClick={() => props.onWrite("never")}>
              {c.actionNever}
              <Key>4</Key>
            </Button>
          ) : null}
          {deciding ? <VocifySpinner size={12} /> : null}
        </div>
        {message ? (
          <p className="px-1 text-sm text-destructive" role="alert">
            {message}
          </p>
        ) : null}
      </CaseCard>
    );
  }

  return (
    <div className="mx-auto w-full max-w-2xl space-y-5">
      {header}
      {body}
    </div>
  );
}

/** The trial of one call type wired to the API: the case flow, then the result. */
export function TrialRunner({ motionKey, onChanged, onBack }: { motionKey: string | null; onChanged: () => void; onBack: () => void }) {
  const { t } = useLanguage();
  const c = t.product.pb2.improve;
  const trial = useTrial({ motionKey, onChanged });
  const [value, setValue] = useState("");
  const { phase, status } = trial;

  // 1 to 4 answer the case on screen, as the buttons show; never while typing.
  useEffect(() => {
    if (status !== "ready" || phase.kind !== "judging" || trial.finished || !trial.run || trial.deciding) return;
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (event.metaKey || event.ctrlKey || event.altKey || target?.closest("input, textarea, [contenteditable]")) return;
      const card = trial.run?.card;
      if (event.key === "1" && card) void trial.decide("approve");
      else if (event.key === "2") trial.write("say");
      else if (event.key === "3") void trial.decide("unknown");
      else if (event.key === "4" && card?.source_id) trial.write("never");
      else return;
      event.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [status, phase.kind, trial]);

  if (trial.finished && trial.trial) {
    const names = {
      kinds: t.product.playbookObjectionCategories as Record<string, string>,
      question: c.topicQuestion,
      none: c.topicNone,
      unknown: c.topicUnknown,
    };
    return (
      <TrialResultView
        trial={trial.trial}
        weakTopics={trial.trial.result.weak_topics.map((topic) => topicLabel(topic, names))}
        activation={trial.activation}
        problem={trial.problem ? (c.errors[trial.problem] ?? c.errors.unknown) : null}
        onActivate={() => void trial.activate()}
        onAgain={() => void trial.again()}
        onResume={trial.trial.current_id ? trial.resume : null}
        onBack={onBack}
      />
    );
  }

  const submit = async (text: string) => {
    if (phase.kind !== "writing") return;
    const saved =
      phase.mode === "never"
        ? await trial.decide("never_say", text)
        : phase.mode === "branch"
          ? await trial.decide("branch", text, phase.situation)
          : await trial.decide("corrected", text);
    if (saved) setValue("");
  };

  return (
    <TrialRunnerView
      status={trial.status}
      trial={trial.trial}
      caseId={trial.caseId}
      run={trial.run}
      phase={phase}
      deciding={trial.deciding}
      problem={trial.problem}
      value={value}
      onValue={setValue}
      onApprove={() => void trial.decide("approve")}
      onUnknown={() => void trial.decide("unknown")}
      onWrite={(mode) => {
        setValue("");
        trial.write(mode);
      }}
      onSubmitWriting={(text) => void submit(text)}
      onCancelWriting={() => {
        setValue("");
        trial.cancelWriting();
      }}
      onOwn={() => {
        if (phase.kind === "writing") void trial.decide("own", value.trim(), phase.situation).then((saved) => saved && setValue(""));
      }}
      onSimilarSame={trial.next}
      onSimilarOther={() => {
        setValue("");
        trial.writeBranch();
      }}
      onFinish={trial.finish}
      onRetry={() => (trial.trial ? trial.retryRun() : void trial.reload())}
    />
  );
}
