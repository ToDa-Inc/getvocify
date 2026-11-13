import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowUpRight,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  DoorOpen,
  GraduationCap,
  Lightbulb,
  MessageSquareWarning,
  Sparkles,
  Trophy,
  type LucideIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Toggle } from "@/components/ui/toggle";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { Bubble, StateTag } from "@/features/coaching/rep/OccurrencePager";
import {
  SUGGESTIONS_QUERY,
  suggestionsApi,
  type DismissReason,
  type Suggestion,
  type SuggestionAnswer,
  type SuggestionKind,
  type SuggestionsBody,
} from "@/features/playbooks/suggestionsApi";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";
import { ApiError } from "@/shared/lib/api-client";

const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card}`;
const KINDS: readonly SuggestionKind[] = ["objection", "question", "worked", "opportunity"];
const ICON: Record<SuggestionKind, LucideIcon> = { objection: MessageSquareWarning, question: CircleHelp, worked: Trophy, opportunity: DoorOpen };
// Each kind its own quiet colour, so the list reads at a glance: what pushes back, what they ask, what worked, what opens.
const TONE: Record<SuggestionKind, string> = {
  objection: "bg-warning/10 text-warning",
  question: "bg-secondary text-foreground/70",
  worked: "bg-success/10 text-success",
  opportunity: "bg-beige/15 text-beige",
};
// The ones that cost most show; the rest wait behind one quiet button, so the page says where to start.
const TOP = 3;
const REASONS: readonly DismissReason[] = ["isolated", "not_applicable", "covered"];

function errorCode(error: unknown): string {
  if (error instanceof ApiError) {
    const detail = (error.data as { detail?: { code?: string } } | null | undefined)?.detail;
    if (detail?.code) return detail.code;
  }
  return "unknown";
}

function useCopy() {
  return useLanguage().t.product.pb2.suggestions;
}

/** Where the draft comes from, as one chip: the colleague it worked for, or Vocify. Details in the tooltip. */
function DraftSource({ suggestion }: { suggestion: Suggestion }) {
  const c = useCopy();
  if (!suggestion.draft_from) return null;
  const colleague = suggestion.draft_from === "colleague";
  const name = colleague ? suggestion.examples.find((e) => e.after === "advanced")?.rep || suggestion.reps[0] || "" : "";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span tabIndex={0} className="inline-flex items-center gap-1 rounded-full bg-success/10 px-2 py-0.5 text-[11px] font-medium text-success focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          {colleague ? <Check aria-hidden className="h-3 w-3" strokeWidth={2} /> : <Sparkles aria-hidden className="h-3 w-3" strokeWidth={1.75} />}
          {colleague ? name || c.kinds.worked : "Vocify"}
        </span>
      </TooltipTrigger>
      <TooltipContent side="top">{colleague ? c.fromColleague.replace("{name}", name) : c.fromVocify}</TooltipContent>
    </Tooltip>
  );
}

/** One example call: the exchange as it happened (what was meant, the exact words behind a quote icon) and its date. */
function Example({ suggestion }: { suggestion: Suggestion }) {
  // A colleague's words that worked are the draft right below: shown once, there, with their name.
  const isDraft = (quote: string, said: string | null) =>
    suggestion.draft_from === "colleague" && !!suggestion.draft && (suggestion.draft === quote || suggestion.draft === said);
  const { t, language } = useLanguage();
  const c = useCopy();
  const p = t.product;
  const [index, setIndex] = useState(0);
  const example = suggestion.examples[Math.min(index, suggestion.examples.length - 1)];
  if (!example) return null;
  const day = new Date(example.observed_at).toLocaleDateString(language === "EN" ? "en-GB" : "es-ES", { day: "numeric", month: "short" });
  const total = suggestion.examples.length;
  return (
    <div className="space-y-2.5">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        {example.rep ? <span>{example.rep}</span> : null}
        <Link to={`/dashboard/memos/${example.memo_id}`} aria-label={c.openCall} className="inline-flex items-center gap-0.5 hover:text-foreground">
          {day}
          <ArrowUpRight aria-hidden className="h-3 w-3" />
        </Link>
        {total > 1 ? (
          <span className="ml-auto inline-flex items-center">
            <button type="button" aria-label={p.coachPrevious} disabled={index === 0} onClick={() => setIndex(index - 1)} className={cn(THEME_TOKENS.interaction.iconButton, "h-7 w-7")}>
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="min-w-9 text-center tabular-nums">{index + 1}/{total}</span>
            <button type="button" aria-label={p.coachNext} disabled={index === total - 1} onClick={() => setIndex(index + 1)} className={cn(THEME_TOKENS.interaction.iconButton, "h-7 w-7")}>
              <ChevronRight className="h-4 w-4" />
            </button>
          </span>
        ) : null}
      </div>
      {example.turns.filter((turn) => !(turn.who === "rep" && isDraft(turn.quote, turn.said))).map((turn, i) => (
        <Bubble key={i} kind={turn.who === "client" ? "prospect" : "you"} caption={turn.who === "client" ? p.coachProspectSaid : p.coachYouSaid} said={turn.said}>
          {turn.quote}
        </Bubble>
      ))}
    </div>
  );
}

/** The tags of a suggestion's row: how often, who, and what it cost. */
function Meta({ suggestion, showType }: { suggestion: Suggestion; showType: boolean }) {
  const c = useCopy();
  // How often only says something once it happened more than once; who, the first two names.
  const parts = [
    suggestion.count > 1 ? c.calls.replace("{count}", String(suggestion.count)) : null,
    suggestion.reps.length ? suggestion.reps.slice(0, 2).join(", ") + (suggestion.reps.length > 2 ? ` +${suggestion.reps.length - 2}` : "") : null,
    showType ? suggestion.motion_label : null,
  ].filter(Boolean);
  return (
    <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
      {parts.length ? <span className="tabular-nums">{parts.join(" · ")}</span> : null}
      {suggestion.lost ? <StateTag tone="bad">{c.lost} · {suggestion.lost}</StateTag> : null}
      {suggestion.unanswered ? <StateTag tone="bad">{c.unanswered} · {suggestion.unanswered}</StateTag> : null}
    </span>
  );
}

/** Set it aside with a reason in one tap; «Ya cubierta» asks which answer covers it. */
function DismissChips({ suggestion, answers, busy, onDismiss }: {
  suggestion: Suggestion; answers: SuggestionAnswer[]; busy: boolean; onDismiss: (reason: DismissReason, coveredBy?: string) => void;
}) {
  const c = useCopy();
  const { t } = useLanguage();
  const categories = t.product.playbookObjectionCategories as Record<string, string>;
  const [covered, setCovered] = useState(false);
  return (
    <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label={c.dismiss}>
      {REASONS.map((reason) =>
        reason === "covered" && !answers.length ? null : (
          <Tooltip key={reason}>
            <TooltipTrigger asChild>
              <span className="inline-flex">
                <Toggle
                  variant="chip"
                  size="sm"
                  disabled={busy}
                  pressed={reason === "covered" && covered}
                  onPressedChange={() => (reason === "covered" ? setCovered((now) => !now) : onDismiss(reason))}
                >
                  {c.reasons[reason]}
                </Toggle>
              </span>
            </TooltipTrigger>
            <TooltipContent side="top">{c.reasonsHint[reason]}</TooltipContent>
          </Tooltip>
        ),
      )}
      {covered ? (
        <Select onValueChange={(value) => onDismiss("covered", value)} disabled={busy}>
          <SelectTrigger variant="chip" className="max-w-64" aria-label={c.coveredPick}>
            <SelectValue placeholder={c.coveredPick} />
          </SelectTrigger>
          <SelectContent>
            {answers.map((answer) => (
              <SelectItem key={answer.id} value={answer.id}>
                {answer.label || categories[answer.category] || answer.category}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : null}
    </div>
  );
}

/** One suggestion: the row (kind icon, title, tags) and, open, the example call, the draft to take and the way out. */
function SuggestionRow({ suggestion, answers, open, showType, top = false, onToggle, onDone }: {
  suggestion: Suggestion;
  answers: SuggestionAnswer[];
  open: boolean;
  showType: boolean;
  /** One of the few that cost most: drawn a size up. */
  top?: boolean;
  onToggle: () => void;
  onDone: (body: SuggestionsBody) => void;
}) {
  const c = useCopy();
  const queryClient = useQueryClient();
  const [text, setText] = useState(suggestion.draft ?? "");
  const [dismissing, setDismissing] = useState(false);
  useEffect(() => setText(suggestion.draft ?? ""), [suggestion.key, suggestion.draft]);
  const Icon = ICON[suggestion.kind];
  const answerKind = suggestion.kind === "objection" || suggestion.kind === "question";
  const where = (answerKind ? c.addAnswer : c.addConduct).replace("{type}", suggestion.motion_label);
  // «Completar con Vocify»: only for an answer with nothing to start from, and only from the company's own material.
  const complete = useMutation({
    mutationFn: () => suggestionsApi.draft(suggestion.key),
    onSuccess: ({ text: written }) => (written ? setText(written) : toast(c.draftNone)),
    onError: () => toast(c.draftNone),
  });

  const accept = useMutation({
    mutationFn: () => suggestionsApi.accept(suggestion.key, text.trim()),
    onSuccess: (body) => {
      onDone(body);
      toast((body.published ? c.added : c.addedDraft).replace("{type}", suggestion.motion_label), {
        icon: <GraduationCap className="h-4 w-4 text-success" strokeWidth={1.75} />,
      });
    },
    onError: (error) => toast(c.errors[errorCode(error)] ?? c.errors.unknown),
  });
  const dismiss = useMutation({
    mutationFn: ({ reason, coveredBy }: { reason: DismissReason; coveredBy?: string }) => suggestionsApi.dismiss(suggestion.key, reason, coveredBy),
    onSuccess: (body, { reason }) => {
      onDone(body);
      toast(`${c.dismissed} · ${c.reasons[reason]}`, {
        action: {
          label: c.undo,
          onClick: () => void suggestionsApi.undo(suggestion.key).then((restored) => queryClient.setQueryData(SUGGESTIONS_QUERY, restored)),
        },
      });
    },
    onError: (error) => toast(c.errors[errorCode(error)] ?? c.errors.unknown),
  });
  const busy = accept.isPending || dismiss.isPending || complete.isPending;

  return (
    <li className="border-t border-border/50 first:border-t-0">
      <button
        type="button"
        aria-expanded={open}
        onClick={onToggle}
        className={cn("flex w-full items-start gap-3 px-4 py-3.5 text-left md:px-5", THEME_TOKENS.interaction.rowHover)}
      >
        <Tooltip>
          <TooltipTrigger asChild>
            <span className={cn("mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full", TONE[suggestion.kind])}>
              <Icon aria-hidden className="h-3.5 w-3.5" strokeWidth={1.5} />
              <span className="sr-only">{c.kinds[suggestion.kind]}</span>
            </span>
          </TooltipTrigger>
          <TooltipContent side="top">{c.kinds[suggestion.kind]}</TooltipContent>
        </Tooltip>
        <span className="min-w-0 flex-1 space-y-1">
          <span className={cn("block font-medium leading-snug text-foreground", top ? "text-[16px]" : "text-[15px]")}>{suggestion.title}</span>
          <Meta suggestion={suggestion} showType={showType} />
        </span>
        <ChevronDown aria-hidden className={cn("mt-1 h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-150 motion-reduce:transition-none", open && "rotate-180")} />
      </button>
      {open ? (
        <div className={cn("space-y-4 px-4 pb-5 md:px-5 md:pl-[3.75rem]", THEME_TOKENS.motion.fadeIn)}>
          <Example suggestion={suggestion} />
          {suggestion.why && suggestion.kind !== "worked" ? <p className="text-[13.5px] leading-snug text-muted-foreground">{suggestion.why}</p> : null}
          <div className="space-y-2">
            <div className="flex items-center justify-end gap-2">
              <DraftSource suggestion={suggestion} />
            </div>
            <label className="flex items-start gap-2 rounded-2xl rounded-br-md border border-success/25 bg-success/10 px-3.5 py-2.5 focus-within:ring-1 focus-within:ring-success/40">
              <Lightbulb aria-hidden className="mt-1 h-3.5 w-3.5 shrink-0 text-success" strokeWidth={1.75} />
              <span className="sr-only">{c.draftLabel}</span>
              <textarea
                value={text}
                rows={Math.min(6, Math.max(2, Math.ceil(text.length / 70)))}
                placeholder={complete.isPending ? c.completing : c.draftPlaceholder}
                maxLength={1200}
                disabled={busy}
                onChange={(event) => setText(event.target.value)}
                className={cn(
                  "min-w-0 flex-1 resize-none bg-transparent text-[14.5px] font-medium leading-snug text-foreground placeholder:font-normal placeholder:text-muted-foreground focus:outline-none",
                  complete.isPending && "ask-shimmer",
                )}
              />
              {answerKind && !text.trim() ? (
                <Button type="button" variant="quiet" size="text" className="shrink-0 self-end" disabled={busy} onClick={() => complete.mutate()}>
                  {complete.isPending ? <VocifySpinner size={12} /> : <Sparkles aria-hidden strokeWidth={1.5} />}
                  {c.complete}
                </Button>
              ) : null}
            </label>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3">
            {dismissing ? (
              <DismissChips suggestion={suggestion} answers={answers} busy={busy} onDismiss={(reason, coveredBy) => dismiss.mutate({ reason, coveredBy })} />
            ) : (
              <Button type="button" variant="quiet" size="text" disabled={busy} onClick={() => setDismissing(true)}>
                {c.dismiss}
              </Button>
            )}
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="inline-flex">
                  <Button type="button" size="sm" disabled={busy || !text.trim()} onClick={() => accept.mutate()}>
                    {accept.isPending ? <VocifySpinner size={12} /> : <Check aria-hidden strokeWidth={1.75} />}
                    {c.addToPlaybook}
                  </Button>
                </span>
              </TooltipTrigger>
              <TooltipContent side="top">{where}</TooltipContent>
            </Tooltip>
          </div>
        </div>
      ) : null}
    </li>
  );
}

export type SuggestionsInboxViewProps = {
  body: SuggestionsBody;
  onDone: (body: SuggestionsBody) => void;
};

/**
 * «Sugerencias»: what the team's calls taught, best first, for the head of sales to take into the playbook with their
 * own words or set aside with a reason Vocify learns from. One open at a time; the first one is open on arrival.
 */
export function SuggestionsInboxView({ body, onDone }: SuggestionsInboxViewProps) {
  const c = useCopy();
  const [kind, setKind] = useState<SuggestionKind | "all">("all");
  const [openKey, setOpenKey] = useState<string | null>(body.suggestions[0]?.key ?? null);
  const [expanded, setExpanded] = useState(false);
  const present = KINDS.filter((k) => body.suggestions.some((s) => s.kind === k));
  const shown = body.suggestions.filter((s) => kind === "all" || s.kind === kind);
  const first = shown.slice(0, TOP);
  const rest = shown.slice(TOP);
  const showType = new Set(body.suggestions.map((s) => s.motion)).size > 1;
  const row = (suggestion: Suggestion, top: boolean) => (
    <SuggestionRow
      key={suggestion.key}
      suggestion={suggestion}
      answers={body.answers[suggestion.motion] ?? []}
      open={openKey === suggestion.key}
      showType={showType}
      top={top}
      onToggle={() => setOpenKey((now) => (now === suggestion.key ? null : suggestion.key))}
      onDone={(next) => {
        const after = next.suggestions.filter((s) => kind === "all" || s.kind === kind);
        setOpenKey(after[0]?.key ?? null);
        onDone(next);
      }}
    />
  );
  const count = (k: SuggestionKind | "all") => (k === "all" ? body.suggestions.length : body.suggestions.filter((s) => s.kind === k).length);

  return (
    <section aria-labelledby="suggestions-title" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          {/* The hub above already names the view; the heading stays for screen readers. */}
          <h2 id="suggestions-title" className="sr-only">
            {c.title}
          </h2>
          {body.learned ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <span tabIndex={0} className="inline-flex items-center gap-1 rounded-full bg-success/10 px-2 py-0.5 text-[11px] font-medium text-success focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                  <GraduationCap aria-hidden className="h-3 w-3" strokeWidth={1.75} />
                  {c.learned.replace("{count}", String(body.learned))}
                </span>
              </TooltipTrigger>
              <TooltipContent side="top">{c.learnedHint}</TooltipContent>
            </Tooltip>
          ) : null}
        </div>
        {present.length > 1 ? (
          <Segmented<SuggestionKind | "all">
            aria-label={c.filterLabel}
            value={kind}
            onValueChange={(next) => {
              // The first of the kind opens, as the first of all does on arrival.
              setKind(next);
              setOpenKey(body.suggestions.find((s) => next === "all" || s.kind === next)?.key ?? null);
              setExpanded(false);
            }}
            options={[
              { value: "all", label: <span>{c.all} <span className="tabular-nums text-muted-foreground">{count("all")}</span></span> },
              ...present.map((k) => ({ value: k, label: <span>{c.kindsMany[k]} <span className="tabular-nums text-muted-foreground">{count(k)}</span></span> })),
            ]}
          />
        ) : null}
      </div>
      {shown.length ? (
        <>
          <ul className={cn(card, "overflow-hidden")}>{first.map((suggestion) => row(suggestion, true))}</ul>
          {rest.length ? (
            expanded ? (
              <ul className={cn(card, "overflow-hidden")}>{rest.map((suggestion) => row(suggestion, false))}</ul>
            ) : (
              <Button type="button" variant="quiet" size="text" onClick={() => setExpanded(true)}>
                <ChevronDown aria-hidden className="h-3.5 w-3.5" strokeWidth={1.5} />
                {c.more.replace("{count}", String(rest.length))}
              </Button>
            )
          ) : null}
        </>
      ) : (
        <div className={cn(card, "flex flex-col items-center gap-2 px-6 py-12 text-center")}>
          <GraduationCap aria-hidden className="h-6 w-6 text-success" strokeWidth={1.5} />
          <p className="text-[15px] font-medium text-foreground">{c.emptyTitle}</p>
          <p className="max-w-sm text-[13px] text-muted-foreground">{c.emptyLine}</p>
        </div>
      )}
    </section>
  );
}

/** The inbox wired to the company's suggestions. */
export function SuggestionsInbox({ onChanged }: { onChanged?: () => void }) {
  const c = useCopy();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: SUGGESTIONS_QUERY, queryFn: suggestionsApi.list, staleTime: 60_000 });
  if (query.isPending) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-7 w-40" />
        <Skeleton className="h-64 w-full rounded-2xl" />
      </div>
    );
  }
  if (query.isError || !query.data) {
    return (
      <div className={cn(card, "flex items-center justify-between gap-3 p-5")}>
        <p className={THEME_TOKENS.typography.body}>{c.loadFailed}</p>
        <Button type="button" variant="outline" size="sm" onClick={() => void query.refetch()}>
          {c.retry}
        </Button>
      </div>
    );
  }
  return (
    <SuggestionsInboxView
      body={query.data}
      onDone={(body) => {
        queryClient.setQueryData(SUGGESTIONS_QUERY, body);
        onChanged?.();
      }}
    />
  );
}

/** Equipo's way to the suggestions: how many are waiting, one tap from the playbook view that holds them. */
export function SuggestionsLink() {
  const c = useCopy();
  const query = useQuery({ queryKey: SUGGESTIONS_QUERY, queryFn: suggestionsApi.list, retry: false, staleTime: 60_000 });
  const count = query.data?.suggestions.length ?? 0;
  if (!count) return null;
  return (
    <Button asChild variant="outline" size="sm">
      <Link to="/dashboard/playbook?view=suggestions">
        <GraduationCap aria-hidden strokeWidth={1.5} />
        {c.title}
        <span className="tabular-nums text-muted-foreground">{count}</span>
      </Link>
    </Button>
  );
}
