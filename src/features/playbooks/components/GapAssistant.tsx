import { useEffect, useState } from "react";
import { ArrowDownToLine, Check, HelpCircle, ListOrdered, MessageSquareQuote, Split } from "lucide-react";
import { Button } from "@/components/ui/button";
import { IconAction } from "@/components/ui/icon-action";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Skeleton } from "@/components/ui/skeleton";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import type { GapSession, GapView } from "@/features/playbooks/assistantApi";
import { AnswerBox } from "@/features/playbooks/components/AnswerBox";
import { CardBubble, SavedBubble } from "@/features/playbooks/components/Bubbles";
import { SegmentMeter, type SegmentTone } from "@/features/playbooks/components/SegmentMeter";
import type { SourceInput } from "@/features/playbooks/components/PlaybookStart";
import { useAssistant, type AssistantStatus } from "@/features/playbooks/hooks/useAssistant";
import { useLanguage } from "@/lib/i18n";
import { progressText, splitQuestion } from "@/lib/playbook-assistant";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card}`;

export type GapAssistantViewProps = {
  status: AssistantStatus;
  session: GapSession | null;
  saved: { line: string } | null;
  saving: boolean;
  undoing: boolean;
  /** The message to show under the field, already in the person's language. */
  problem: string | null;
  value: string;
  onValue: (value: string) => void;
  onAnswer: (source: SourceInput) => void;
  onSkip: () => void;
  onUndo: () => void;
  onTry: () => void;
  onBack: () => void;
  onRetry: () => void;
};

const KIND_ICON = { real: MessageSquareQuote, topic: HelpCircle, conflict: Split, process: ListOrdered } as const;

/** What kind of gap it is, as a chip; for one from calls, how many times, with the window on hover. */
function GapChip({ gap }: { gap: GapView }) {
  const { t } = useLanguage();
  const c = t.product.pb2.improve;
  const Icon = KIND_ICON[gap.kind as keyof typeof KIND_ICON] ?? HelpCircle;
  const name = { real: c.gapReal, topic: c.gapTopic, conflict: c.gapConflict, process: c.gapProcess }[gap.kind as keyof typeof KIND_ICON] ?? c.gapTopic;
  const chip = (
    <span className="inline-flex h-6 items-center gap-1.5 rounded-full bg-secondary/70 px-2.5 text-[12px] font-medium text-muted-foreground">
      <Icon aria-hidden className="h-3.5 w-3.5" strokeWidth={1.5} />
      {name}
      {gap.kind === "real" && gap.seen > 1 ? <span className="tabular-nums text-foreground">· {gap.seen}</span> : null}
    </span>
  );
  if (gap.kind !== "real" || gap.seen < 1) return chip;
  return (
    <Tooltip>
      <TooltipTrigger asChild>{chip}</TooltipTrigger>
      <TooltipContent>{c.gapSeen.replace("{count}", String(gap.seen))}</TooltipContent>
    </Tooltip>
  );
}

/** The thing to answer, as the hero: the customer's words, the call type, or the two versions to choose between. A gap
 * saved before these fields existed falls back to its sentence. */
function GapSubject({ gap, saving, onPick }: { gap: GapView; saving: boolean; onPick: (option: string) => void }) {
  const { t } = useLanguage();
  const c = t.product.pb2.improve;
  const hero = "text-[19px] font-medium leading-snug tracking-tight text-foreground";
  if (gap.kind === "conflict" && gap.options?.length) {
    return (
      <div className="space-y-3">
        {gap.example ? <h3 id="gap-ask" className={hero}>{gap.example}</h3> : null}
        <div className="grid gap-2 sm:grid-cols-2">
          {gap.options.map((option) => (
            <div key={option} className={cn("flex flex-col justify-between gap-3 border border-border/70 p-4", THEME_TOKENS.radius.control)}>
              <p className="text-[14.5px] leading-relaxed text-foreground">{option}</p>
              <Button type="button" variant="outline" size="sm" className="self-start" disabled={saving} onClick={() => onPick(option)}>
                {c.gapPick}
              </Button>
            </div>
          ))}
        </div>
      </div>
    );
  }
  const quote = gap.kind === "real" || gap.kind === "topic" ? (gap.example ?? splitQuestion(gap.question, gap.example).quote) : null;
  if (quote) {
    return (
      <blockquote id="gap-ask" className={cn(hero, "border-l-2 border-beige/60 pl-4")}>
        {quote}
      </blockquote>
    );
  }
  return <h3 id="gap-ask" className={hero}>{gap.kind === "process" && gap.example ? gap.example : gap.question}</h3>;
}

/** One segment per question: green answered, grey left for later, beige the one on screen, pale the ones to come. */
function Meter({ session }: { session: GapSession }) {
  const { t } = useLanguage();
  const done = session.answered;
  const left = done + session.skipped;
  const segments = Array.from({ length: session.total }, (_, index): SegmentTone =>
    index < done ? "success" : index < left ? "muted" : index === left ? "current" : "pending",
  );
  return <SegmentMeter segments={segments} label={progressText(session, t.product.pb2.improve.of)} />;
}

/**
 * "Lo que falta": Vocify asks what the playbook still lacks, one question at a time. The customer's own words come as a
 * quote (Coaching's bubble), the answer goes in Inicio's composer (type, dictate or attach), and what was saved shows
 * at once with a way back. Pure view: the container below holds the state, the preview page feeds it examples.
 */
export function GapAssistantView(props: GapAssistantViewProps) {
  const { status, session, saved, saving, undoing, problem, value, onValue, onAnswer, onSkip, onUndo, onTry, onBack, onRetry } = props;
  const { t } = useLanguage();
  const c = t.product.pb2.improve;
  const current = session?.current ?? null;
  const header = (
    <header className="flex flex-wrap items-end justify-between gap-3">
      <h2 className={THEME_TOKENS.typography.panelTitle}>{c.assistantTitle}</h2>
      {session && status === "ready" ? (
        <div className="flex items-center gap-2">
          <Meter session={session} />
          <span aria-hidden className="text-xs tabular-nums text-muted-foreground">{progressText(session, "/").replace(" / ", "/")}</span>
        </div>
      ) : null}
    </header>
  );

  let body;
  if (status === "loading") {
    body = (
      <div className={cn(card, "space-y-3 p-6")} role="status" aria-busy="true">
        <Skeleton className="h-3 w-1/3 motion-reduce:animate-none" />
        <Skeleton className="h-6 w-3/4 motion-reduce:animate-none" />
        <Skeleton className="h-28 w-full rounded-[22px] motion-reduce:animate-none" />
        <span className="sr-only">{c.assistantLoading}</span>
      </div>
    );
  } else if (status === "not_activated") {
    body = <p className={cn(card, "p-5", THEME_TOKENS.typography.body)}>{c.notActivated}</p>;
  } else if (status === "error") {
    body = (
      <div className={cn(card, "flex flex-wrap items-center gap-3 p-5")} role="alert">
        <p className={THEME_TOKENS.typography.body}>{c.loadFailed}</p>
        <Button type="button" variant="outline" size="sm" onClick={onRetry}>
          {c.retry}
        </Button>
      </div>
    );
  } else if (status === "done" || !current) {
    body = (
      <section className={cn(card, "space-y-4 p-6", THEME_TOKENS.motion.fadeIn)} aria-labelledby="gap-done">
        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-success/10 text-success">
          <Check aria-hidden className="h-4 w-4" strokeWidth={1.75} />
        </span>
        <div className="space-y-1">
          <h3 id="gap-done" className="text-[19px] font-medium leading-snug tracking-tight text-foreground">
            {c.doneTitle}
          </h3>
          <p className={THEME_TOKENS.typography.body}>{c.doneLead}</p>
          {session ? (
            <p className="text-[13px] text-muted-foreground">
              {c.doneCount.replace("{answered}", String(session.answered)).replace("{skipped}", String(session.skipped))}
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" onClick={onTry}>
            {c.doneTry}
          </Button>
          <Button type="button" variant="quiet" size="text" onClick={onBack}>
            {c.doneBack}
          </Button>
        </div>
      </section>
    );
  } else {
    body = (
      <section key={current.key} className={cn(card, "space-y-5 p-5 md:p-6", THEME_TOKENS.motion.fadeIn)} aria-labelledby="gap-ask">
        <GapChip gap={current} />
        <GapSubject gap={current} saving={saving} onPick={(option) => onAnswer({ kind: "text", payload: option })} />
        {current.draft ? (
          <div className="space-y-1.5">
            <p className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
              <Check aria-hidden className="h-3.5 w-3.5 text-success" strokeWidth={1.75} />
              {c.gapDraftLabel}
            </p>
            <div className="flex items-start gap-2">
              <CardBubble className="min-w-0 flex-1">{current.draft}</CardBubble>
              <IconAction label={c.gapDraftUse} disabled={saving || value.trim() === current.draft} onClick={() => onValue(current.draft ?? "")}>
                <ArrowDownToLine strokeWidth={1.5} />
              </IconAction>
            </div>
          </div>
        ) : null}
        <AnswerBox
          value={value}
          onChange={onValue}
          onSubmit={onAnswer}
          busy={saving}
          focusKey={current.key}
          copy={{
            placeholder: c.answerPlaceholder,
            submit: c.answerSave,
            attach: c.fileAttach,
            removeFile: c.fileRemove,
            unsupported: c.fileUnsupported,
            hint: c.answerHint,
          }}
          footer={
            <Button type="button" variant="quiet" size="text" disabled={saving} onClick={onSkip}>
              {c.answerSkip}
            </Button>
          }
        />
        {saving ? (
          <p className="inline-flex items-center gap-2 px-1 text-sm text-muted-foreground" role="status">
            <VocifySpinner size={12} />
            {c.answerSaving}
          </p>
        ) : null}
        {problem ? (
          <p className="px-1 text-sm text-destructive" role="alert">
            {problem}
          </p>
        ) : null}
      </section>
    );
  }

  return (
    <div className="mx-auto w-full max-w-2xl space-y-5">
      {header}
      {saved ? (
        <SavedBubble
          title={c.savedTitle}
          action={
            <Button type="button" variant="quiet" size="text" disabled={undoing} onClick={onUndo}>
              {undoing ? c.undoing : c.undo}
            </Button>
          }
        >
          {saved.line}
        </SavedBubble>
      ) : null}
      {body}
    </div>
  );
}

/** The guided questions of one call type, wired to the API. */
export function GapAssistant({ motionKey, onChanged, onTry, onBack }: { motionKey: string | null; onChanged: () => void; onTry: () => void; onBack: () => void }) {
  const { t } = useLanguage();
  const c = t.product.pb2.improve;
  const assistant = useAssistant({ motionKey, onChanged });
  const [value, setValue] = useState("");
  const currentKey = assistant.session?.current?.key;
  const pending = assistant.session?.pending_text ?? "";

  // A save that failed after the text was read keeps it on the server: it comes back into the field.
  useEffect(() => {
    if (pending) setValue((now) => now || pending);
  }, [currentKey, pending]);

  return (
    <GapAssistantView
      status={assistant.status}
      session={assistant.session}
      saved={assistant.saved}
      saving={assistant.saving}
      undoing={assistant.undoing}
      problem={assistant.problem ? (c.errors[assistant.problem] ?? c.errors.unknown) : null}
      value={value}
      onValue={setValue}
      onAnswer={(source) => void assistant.answer(source).then((saved) => saved && setValue(""))}
      onSkip={() => void assistant.skip().then(() => setValue(""))}
      onUndo={() => void assistant.undo()}
      onTry={onTry}
      onBack={onBack}
      onRetry={() => void assistant.reload()}
    />
  );
}
