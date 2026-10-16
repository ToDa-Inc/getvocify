import { useState } from "react";
import { Check, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Skeleton } from "@/components/ui/skeleton";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import type { QueueGroup, QueueMoment } from "@/features/playbooks/assistantApi";
import { AnswerBox } from "@/features/playbooks/components/AnswerBox";
import { CardBubble, QuoteBubble } from "@/features/playbooks/components/Bubbles";
import { ImproveStatsSkeleton, ImproveStatsView } from "@/features/playbooks/components/ImproveStats";
import { SegmentMeter } from "@/features/playbooks/components/SegmentMeter";
import { useImprove, type ImproveController, type ImproveProblem, type Publication } from "@/features/playbooks/hooks/useImprove";
import { useLanguage } from "@/lib/i18n";
import { queueMeter, verdictChoices } from "@/lib/playbook-assistant";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card}`;
const fill = (text: string, values: Record<string, string | number>) => text.replace(/\{(\w+)\}/g, (_, key: string) => String(values[key] ?? ""));

export type WritingMode = "correct" | "branch" | "new_objection";
export type Writing = { momentId: string; mode: WritingMode };

const CHIP: Record<QueueMoment["mark"], string> = {
  success: "bg-success/10 text-success",
  failed: "bg-warning/10 text-warning",
  unused: "bg-muted text-muted-foreground",
  unknown: "bg-muted text-muted-foreground",
};

/** One real case: what the customer said, what Vocify suggested, what the rep said and what came of it. */
function ReviewCase({
  moment,
  writing,
  value,
  busy,
  acting,
  problem,
  onValue,
  onKeep,
  onWrite,
  onCancel,
  onSubmit,
  onVerdict,
}: {
  moment: QueueMoment;
  writing: Writing | null;
  value: string;
  busy: boolean;
  /** This case is the one a call is in flight for. */
  acting: boolean;
  problem: string | null;
  onValue: (value: string) => void;
  onKeep: () => void;
  onWrite: (mode: WritingMode) => void;
  onCancel: () => void;
  onSubmit: (text: string) => void;
  onVerdict: (resolved: "resolved" | "not_resolved") => void;
}) {
  const { t } = useLanguage();
  const c = t.product.pb2.improve;
  const chip = { success: c.markResolved, failed: c.markNotResolved, unused: c.markUnused, unknown: c.markUnknown }[moment.mark];
  const choices = moment.event_id ? verdictChoices(moment.mark) : [];
  const here = writing?.momentId === moment.id ? writing.mode : null;
  const heading = here === "branch" ? c.branchHere : here === "new_objection" ? c.newHere : c.sayHeading;
  const message = problem ? (c.errors[problem] ?? c.errors.unknown) : null;
  return (
    <li className="space-y-3 border-t border-border/50 px-4 py-4 first:border-t-0 md:px-5">
      <QuoteBubble label={c.caseCustomer}>{moment.client_text}</QuoteBubble>
      {moment.suggestion_text ? <CardBubble label={c.caseSuggested}>{moment.suggestion_text}</CardBubble> : null}
      <div className="space-y-1.5">
        <p className="text-xs font-medium text-muted-foreground">{c.caseRepSaid}</p>
        <p className="text-[14.5px] leading-relaxed text-foreground/85">{moment.rep_text ?? <span className="text-muted-foreground">{c.caseRepUnknown}</span>}</p>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className={cn("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs", CHIP[moment.mark])}>{chip}</span>
          {choices.map((resolved) => (
            <Button key={resolved} type="button" variant="quiet" size="text" className="text-xs" disabled={busy} onClick={() => onVerdict(resolved)}>
              {choices.length === 1 ? c.notSo : resolved === "resolved" ? c.setResolved : c.setNotResolved}
            </Button>
          ))}
        </div>
      </div>
      {here ? (
        <div className="space-y-3 pt-1">
          <h4 className="text-[17px] font-medium leading-snug tracking-tight text-foreground">{heading}</h4>
          <AnswerBox
            value={value}
            onChange={onValue}
            onSubmit={(source) => onSubmit(source.payload)}
            busy={acting}
            allowFile={false}
            focusKey={`${moment.id}:${here}`}
            copy={{ placeholder: c.sayPlaceholder, submit: c.answerSave, attach: c.fileAttach, removeFile: c.fileRemove, unsupported: c.fileUnsupported, hint: c.answerHint }}
            footer={
              <Button type="button" variant="quiet" size="text" disabled={acting} onClick={onCancel}>
                {c.cancel}
              </Button>
            }
          />
          {acting ? (
            <p className="inline-flex items-center gap-2 px-1 text-sm text-muted-foreground" role="status">
              <VocifySpinner size={12} />
              {c.answerSaving}
            </p>
          ) : null}
          {message ? (
            <p className="px-1 text-sm text-destructive" role="alert">
              {message}
            </p>
          ) : null}
        </div>
      ) : (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="outline" size="sm" disabled={busy} onClick={onKeep}>
              {c.actionKeep}
            </Button>
            <Button type="button" size="sm" disabled={busy} onClick={() => onWrite("correct")}>
              {c.actionSay}
            </Button>
            <Button type="button" variant="quiet" size="text" disabled={busy} onClick={() => onWrite("branch")}>
              {c.actionBranch}
            </Button>
            <Button type="button" variant="quiet" size="text" disabled={busy} onClick={() => onWrite("new_objection")}>
              {c.actionNewObjection}
            </Button>
            {acting ? <VocifySpinner size={12} /> : null}
          </div>
          {message ? (
            <p className="px-1 text-sm text-destructive" role="alert">
              {message}
            </p>
          ) : null}
        </div>
      )}
    </li>
  );
}

export type ImproveQueueViewProps = {
  groups: QueueGroup[];
  /** The name of a call type ("Llamada en frío"). */
  typeName: (key: string | null) => string;
  openKey: string | null;
  onOpen: (key: string | null) => void;
  writing: Writing | null;
  value: string;
  /** The case a call is in flight for, if any; every button is off meanwhile. */
  acting: string | null;
  busy: boolean;
  /** The last failure, for the screen to word. */
  problem: ImproveProblem | null;
  onValue: (value: string) => void;
  onKeep: (momentId: string) => void;
  onWrite: (momentId: string, mode: WritingMode) => void;
  onCancel: () => void;
  onSubmit: (text: string) => void;
  onVerdict: (momentId: string, eventId: string, resolved: "resolved" | "not_resolved") => void;
};

const groupKey = (group: QueueGroup) => `${group.sales_motion_key ?? ""}:${group.answer_key}`;

/**
 * "Respuestas que mejorar": the answers that failed three times or more in the last month, as Coaching's list: a row
 * per answer with a meter of how its latest suggestions went and how many cases wait; a row opens to show its cases.
 * Nothing here publishes: the changes go to the draft and a bar at the foot publishes them.
 */
export function ImproveQueueView(props: ImproveQueueViewProps) {
  const { groups, typeName, openKey, onOpen, writing, value, acting, busy, problem, onValue } = props;
  const { t } = useLanguage();
  const c = t.product.pb2.improve;
  const kinds = t.product.playbookObjectionCategories as Record<string, string>;
  const nameOf = (group: QueueGroup) => {
    const answer = group.answer;
    if (answer?.category === "custom") return answer.label || c.queueTitle;
    const category = answer?.category ?? group.answer_key.replace(/^objection:/, "");
    return kinds[category] ?? category;
  };
  return (
    <section className="space-y-3" aria-labelledby="improve-queue">
      <h3 id="improve-queue" className={THEME_TOKENS.typography.groupTitle}>
        {c.queueTitle}
      </h3>
      <ul className={cn(card, "divide-y divide-border/50 overflow-hidden")}>
        {groups.map((group) => {
          const key = groupKey(group);
          const open = openKey === key;
          const cases = group.moments.length;
          return (
            <li key={key}>
              <Collapsible open={open} onOpenChange={(next) => onOpen(next ? key : null)}>
                <CollapsibleTrigger
                  className={cn("flex w-full items-center gap-3 px-4 py-3.5 text-left md:px-5", THEME_TOKENS.interaction.rowHover, "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring")}
                >
                  <span className="min-w-0 flex-1">
                    <span className={cn(THEME_TOKENS.typography.itemTitle, "block truncate")}>{nameOf(group)}</span>
                    <span className="block truncate text-xs text-muted-foreground">{typeName(group.sales_motion_key)}</span>
                  </span>
                  <SegmentMeter className="hidden w-24 sm:flex" segments={queueMeter(group.marks)} label={c.queueMeter} />
                  <span className="shrink-0 text-xs tabular-nums text-muted-foreground">{cases === 1 ? c.queueCaseOne : fill(c.queueCases, { count: cases })}</span>
                  <ChevronDown aria-hidden className={cn("h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200 motion-reduce:transition-none", open && "rotate-180")} strokeWidth={1.5} />
                </CollapsibleTrigger>
                <CollapsibleContent className="border-t border-border/50 bg-secondary/20">
                  <div className="space-y-1.5 px-4 py-4 md:px-5">
                    <p className="text-xs font-medium text-muted-foreground">{c.answerNow}</p>
                    <p className="text-[14.5px] leading-relaxed text-foreground/85">
                      {group.answer?.guidance || <span className="text-muted-foreground">{c.answerGone}</span>}
                    </p>
                  </div>
                  <ul className="border-t border-border/50 bg-card">
                    {group.moments.map((moment) => (
                      <ReviewCase
                        key={moment.id}
                        moment={moment}
                        writing={writing}
                        value={value}
                        busy={busy}
                        acting={acting === moment.id}
                        problem={problem?.at === moment.id ? problem.code : null}
                        onValue={onValue}
                        onKeep={() => props.onKeep(moment.id)}
                        onWrite={(mode) => props.onWrite(moment.id, mode)}
                        onCancel={props.onCancel}
                        onSubmit={props.onSubmit}
                        onVerdict={(resolved) => (moment.event_id ? props.onVerdict(moment.id, moment.event_id, resolved) : undefined)}
                      />
                    ))}
                  </ul>
                </CollapsibleContent>
              </Collapsible>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** The calm state of Coaching when there is nothing to look at. */
export function ImproveEmpty({ judged }: { judged: boolean }) {
  const { t } = useLanguage();
  const c = t.product.pb2.improve;
  return (
    <section className={cn(card, "space-y-3 p-6", THEME_TOKENS.motion.fadeIn)} aria-labelledby="improve-empty">
      <span className="flex h-9 w-9 items-center justify-center rounded-full bg-success/10 text-success">
        <Check aria-hidden className="h-4 w-4" strokeWidth={1.75} />
      </span>
      <div className="space-y-1">
        <h3 id="improve-empty" className="text-[19px] font-medium leading-snug tracking-tight text-foreground">
          {c.queueEmptyTitle}
        </h3>
        <p className={THEME_TOKENS.typography.body}>{judged ? c.queueEmptyLead : c.queueEmptyNoData}</p>
      </div>
    </section>
  );
}

/** The bar at the foot while there are changes waiting: which call types, and the one button that sends them live. */
export function PublishBar({ types, publication, disabled, onPublish }: { types: string[]; publication: Publication; disabled: boolean; onPublish: () => void }) {
  const { t } = useLanguage();
  const c = t.product.pb2.improve;
  if (publication.state === "done" && !types.length) {
    return (
      <div role="status" aria-live="polite" className={cn("flex items-start gap-2.5", THEME_TOKENS.radius.control, "bg-success/10 px-4 py-3", THEME_TOKENS.motion.fadeIn)}>
        <Check aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-success" strokeWidth={1.75} />
        <p className="text-[14.5px] leading-relaxed text-foreground">{publication.failed.length ? fill(c.activateFailed, { names: publication.failed.join(", ") }) : c.published}</p>
      </div>
    );
  }
  if (!types.length) return null;
  return (
    <div className={cn("sticky bottom-3 z-10 flex flex-wrap items-center justify-between gap-3 px-4 py-3", THEME_TOKENS.cards.premium, THEME_TOKENS.radius.card)}>
      <div className="min-w-0">
        <p className={THEME_TOKENS.typography.groupTitle}>{c.publishTitle}</p>
        <p className="truncate text-xs text-muted-foreground">{fill(c.publishIn, { types: types.join(", ") })}</p>
      </div>
      <Button type="button" disabled={disabled} onClick={onPublish}>
        {publication.state === "working" ? <VocifySpinner size={12} tone="onFill" /> : null}
        {publication.state === "working" ? c.publishing : c.publishAction}
      </Button>
    </div>
  );
}

export type ImproveScreenViewProps = {
  status: "loading" | "ready" | "error" | "not_activated";
  stats: ImproveController["stats"];
  queue: ImproveController["queue"];
  refreshing: boolean;
  note: string | null;
  acting: string | null;
  problem: ImproveProblem | null;
  publication: Publication;
  typeName: (key: string | null) => string;
  onRefresh: () => void;
  onRetry: () => void;
  queueProps: Omit<ImproveQueueViewProps, "groups" | "typeName" | "acting" | "busy" | "problem">;
  onPublish: () => void;
};

/** The whole screen: title, the two figures, the queue (or the calm empty state) and the publish bar. */
export function ImproveScreenView(props: ImproveScreenViewProps) {
  const { status, stats, queue, refreshing, note, acting, problem, publication, typeName } = props;
  const { t } = useLanguage();
  const c = t.product.pb2.improve;
  const busy = refreshing || acting !== null || publication.state === "working";
  let body;
  if (status === "loading") {
    body = (
      <div className="space-y-4">
        <ImproveStatsSkeleton />
        <Skeleton className="h-24 w-full motion-reduce:animate-none" />
      </div>
    );
  } else if (status === "not_activated") {
    body = <p className={cn(card, "p-5", THEME_TOKENS.typography.body)}>{c.notActivated}</p>;
  } else if (status === "error" || !stats) {
    body = (
      <div className={cn(card, "flex flex-wrap items-center gap-3 p-5")} role="alert">
        <p className={THEME_TOKENS.typography.body}>{c.loadFailed}</p>
        <Button type="button" variant="outline" size="sm" onClick={props.onRetry}>
          {c.retry}
        </Button>
      </div>
    );
  } else {
    body = (
      <div className="space-y-5">
        <ImproveStatsView coverage={stats.coverage} success={stats.success} refreshing={refreshing} note={note} disabled={busy} onRefresh={props.onRefresh} />
        {queue && queue.groups.length ? (
          <ImproveQueueView {...props.queueProps} groups={queue.groups} typeName={typeName} acting={acting} busy={busy} problem={problem} />
        ) : queue ? (
          <ImproveEmpty judged={Boolean(stats.success?.sample)} />
        ) : null}
        {queue ? <PublishBar types={queue.publish.map((key) => typeName(key))} publication={publication} disabled={busy} onPublish={props.onPublish} /> : null}
        {problem && problem.at === null ? (
          <p className="px-1 text-sm text-destructive" role="alert">
            {c.errors[problem.code] ?? c.errors.unknown}
          </p>
        ) : null}
      </div>
    );
  }
  return (
    <div className="mx-auto w-full max-w-2xl space-y-5">
      <header className="space-y-0.5">
        <h2 className={THEME_TOKENS.typography.panelTitle}>{c.improveTitle}</h2>
        <p className="max-w-md text-[13px] leading-snug text-muted-foreground">{c.improveLead}</p>
      </header>
      {body}
    </div>
  );
}

/** The improvement screen wired to the API. */
export function ImproveScreen({ typeName, onChanged }: { typeName: (key: string | null) => string; onChanged: () => void }) {
  const { t } = useLanguage();
  const c = t.product.pb2.improve;
  const improve = useImprove({ onChanged });
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [writing, setWriting] = useState<Writing | null>(null);
  const [value, setValue] = useState("");
  const note = improve.note
    ? improve.note.judged
      ? fill(c.refreshDone, { judged: improve.note.judged, queued: improve.note.queued })
      : c.refreshNothing
    : null;

  return (
    <ImproveScreenView
      status={improve.status}
      stats={improve.stats}
      queue={improve.queue}
      refreshing={improve.refreshing}
      note={note}
      acting={improve.acting}
      problem={improve.problem}
      publication={improve.publication}
      typeName={typeName}
      onRefresh={() => void improve.refresh()}
      onRetry={() => void improve.reload()}
      onPublish={() => void improve.publish()}
      queueProps={{
        openKey,
        onOpen: (key) => {
          setOpenKey(key);
          setWriting(null);
          setValue("");
          improve.clearProblem();
        },
        writing,
        value,
        onValue: setValue,
        onKeep: (momentId) => void improve.act(momentId, "keep"),
        onWrite: (momentId, mode) => {
          setValue("");
          improve.clearProblem();
          setWriting({ momentId, mode });
        },
        onCancel: () => {
          setWriting(null);
          setValue("");
          improve.clearProblem();
        },
        onSubmit: (text) => {
          if (!writing) return;
          void improve.act(writing.momentId, writing.mode, text).then((done) => {
            if (done) {
              setWriting(null);
              setValue("");
            }
          });
        },
        onVerdict: (momentId, eventId, resolved) => void improve.correctVerdict(momentId, eventId, resolved),
      }}
    />
  );
}
