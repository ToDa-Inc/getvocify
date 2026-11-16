import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import * as SheetPrimitive from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowLeft, Check, ChevronDown, ChevronLeft, ChevronRight, ChevronUp, GraduationCap, Lightbulb, RotateCw, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { IconAction } from "@/components/ui/icon-action";
import { Sheet, SheetPortal } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { Bubble } from "@/features/coaching/rep/OccurrencePager";
import {
  SUGGESTIONS_QUERY,
  suggestionsApi,
  type DismissReason,
  type MomentTurn,
  type Suggestion,
  type SuggestionAfter,
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
// One small dot per kind, so the list reads at a glance: what pushes back, what they ask, what worked, what opened.
const DOT: Record<SuggestionKind, string> = {
  objection: "bg-warning",
  question: "bg-foreground/40",
  worked: "bg-success",
  opportunity: "bg-beige",
};
// What happened right after the rep's reply, as the colour of the mark on that reply.
const AFTER_DOT: Partial<Record<SuggestionAfter, string>> = { advanced: "bg-success", stalled: "bg-warning", ended: "bg-destructive" };
// The list and the open case side by side from this width; below it the case opens over the list.
const SPLIT = "(min-width: 1024px)";

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

function useDay() {
  const { language } = useLanguage();
  return (iso: string | null | undefined) =>
    iso ? new Date(iso).toLocaleDateString(language === "EN" ? "en-GB" : "es-ES", { day: "numeric", month: "short" }) : "";
}

function useSplit(): boolean {
  const [split, setSplit] = useState(() => typeof window !== "undefined" && window.matchMedia(SPLIT).matches);
  useEffect(() => {
    const query = window.matchMedia(SPLIT);
    const onChange = () => setSplit(query.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);
  return split;
}

/** What a suggestion is about, in one line: the reading's context, else how the call ended. */
function contextOf(suggestion: Suggestion): string | null {
  return suggestion.why || suggestion.examples.find((e) => e.summary)?.summary || null;
}

/** Set it aside with a reason in one tap; «Ya cubierta» with the answer that covers it. */
function DismissMenu({ answers, busy, onDismiss }: { answers: SuggestionAnswer[]; busy: boolean; onDismiss: (reason: DismissReason, coveredBy?: string) => void }) {
  const c = useCopy();
  const { t } = useLanguage();
  const categories = t.product.playbookObjectionCategories as Record<string, string>;
  const item = (reason: DismissReason) => (
    <span className="flex flex-col">
      <span className="text-[13.5px] text-foreground">{c.reasons[reason]}</span>
      <span className="text-[12px] text-muted-foreground">{c.reasonsHint[reason]}</span>
    </span>
  );
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button type="button" variant="quiet" size="sm" disabled={busy}>
          {busy ? <VocifySpinner size={12} /> : null}
          {c.dismiss}
          <ChevronDown aria-hidden strokeWidth={1.5} />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-72">
        {(["isolated", "not_applicable"] as const).map((reason) => (
          <DropdownMenuItem key={reason} onSelect={() => onDismiss(reason)}>
            {item(reason)}
          </DropdownMenuItem>
        ))}
        {answers.length ? (
          <DropdownMenuSub>
            <DropdownMenuSubTrigger>{item("covered")}</DropdownMenuSubTrigger>
            <DropdownMenuSubContent className="max-h-80 w-64 overflow-y-auto">
              {answers.map((answer) => (
                <DropdownMenuItem key={answer.id} onSelect={() => onDismiss("covered", answer.id)}>
                  {answer.label || categories[answer.category] || answer.category}
                </DropdownMenuItem>
              ))}
            </DropdownMenuSubContent>
          </DropdownMenuSub>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** The decisions on a suggestion: take it in with the head of sales' words, or set it aside with a reason. */
function useDecide(onDone: (body: SuggestionsBody) => void) {
  const c = useCopy();
  const queryClient = useQueryClient();
  const accept = useMutation({
    mutationFn: ({ key, text }: { key: string; text: string; type: string }) => suggestionsApi.accept(key, text),
    onSuccess: (body, { type }) => {
      onDone(body);
      toast((body.published ? c.added : c.addedDraft).replace("{type}", type));
    },
    onError: (error) => toast(c.errors[errorCode(error)] ?? c.errors.unknown),
  });
  const dismiss = useMutation({
    mutationFn: ({ key, reason, coveredBy }: { key: string; reason: DismissReason; coveredBy?: string }) => suggestionsApi.dismiss(key, reason, coveredBy),
    onSuccess: (body, { key, reason }) => {
      onDone(body);
      toast(`${c.dismissed} · ${c.reasons[reason]}`, {
        action: { label: c.undo, onClick: () => void suggestionsApi.undo(key).then((restored) => queryClient.setQueryData(SUGGESTIONS_QUERY, restored)) },
      });
    },
    onError: (error) => toast(c.errors[errorCode(error)] ?? c.errors.unknown),
  });
  return {
    accept: (suggestion: Suggestion, text: string) => accept.mutate({ key: suggestion.key, text, type: suggestion.motion_label }),
    dismiss: (key: string, reason: DismissReason, coveredBy?: string) => dismiss.mutate({ key, reason, coveredBy }),
    accepting: accept.isPending,
    dismissing: dismiss.isPending ? dismiss.variables?.key ?? null : null,
  };
}
type Decide = ReturnType<typeof useDecide>;

/** A turn just before or after the moment: quieter, there to read it in context. */
function Around({ turn }: { turn: MomentTurn }) {
  const right = turn.who === "rep";
  return (
    <div className={cn("flex", right ? "justify-end" : "justify-start")}>
      <p className={cn("max-w-[85%] rounded-2xl px-3 py-1.5 text-[13px] leading-snug text-muted-foreground", right ? "rounded-br-md bg-foreground/[0.03]" : "rounded-bl-md bg-secondary/35")}>
        {turn.text}
      </p>
    </div>
  );
}

/** The mark on the rep's reply: what happened right after it, by colour; the word in the tooltip. */
function AfterMark({ after }: { after: SuggestionAfter | null }) {
  const { t } = useLanguage();
  const p = t.product;
  const dot = after ? AFTER_DOT[after] : undefined;
  if (!dot || !after) return null;
  const word = { advanced: p.coachAfterAdvanced, stalled: p.coachAfterStalled, ended: p.coachAfterEnded, unknown: p.coachAfterUnknown }[after];
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span tabIndex={0} className="flex h-6 w-6 items-center justify-center rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <span aria-hidden className={cn("h-2 w-2 rounded-full", dot)} />
          <span className="sr-only">{word}</span>
        </span>
      </TooltipTrigger>
      <TooltipContent side="top">{word}</TooltipContent>
    </Tooltip>
  );
}

/** The call a suggestion came from: who and when once (the date opens the call), the turns around it quieter, and the
 * moment itself framed: the client's words and the rep's reply with what happened after it. */
function Moment({ suggestion }: { suggestion: Suggestion }) {
  const c = useCopy();
  const { t } = useLanguage();
  const p = t.product;
  const day = useDay();
  const [index, setIndex] = useState(0);
  useEffect(() => setIndex(0), [suggestion.key]);
  const example = suggestion.examples[Math.min(index, suggestion.examples.length - 1)];
  const quotes = example?.turns.map((turn) => turn.quote) ?? [];
  const around = useQuery({
    queryKey: ["suggestion-moment", example?.memo_id, ...quotes],
    queryFn: () => suggestionsApi.moment(example!.memo_id, quotes),
    enabled: !!example && quotes.length > 0,
    staleTime: Infinity,
    retry: false,
  });
  if (!example) return null;
  // A colleague's words that worked are the draft below: shown there once, not again as their bubble.
  const isDraft = (quote: string, said: string | null) =>
    suggestion.draft_from === "colleague" && !!suggestion.draft && (suggestion.draft === quote || suggestion.draft === said);
  const nearby = around.data?.turns ?? [];
  const first = nearby.findIndex((turn) => turn.moment);
  const last = nearby.length - 1 - [...nearby].reverse().findIndex((turn) => turn.moment);
  const before = first > 0 ? nearby.slice(0, first) : [];
  const after = first >= 0 && last < nearby.length - 1 ? nearby.slice(last + 1) : [];
  const total = suggestion.examples.length;
  const frame = suggestion.kind === "worked" ? "border-success/60" : suggestion.kind === "objection" ? "border-warning/70" : "border-foreground/25";
  return (
    <section className="space-y-2">
      <div className="flex items-center gap-1.5 text-[12.5px] text-muted-foreground">
        {example.rep ? <span>{example.rep} ·</span> : null}
        <Link to={`/dashboard/memos/${example.memo_id}`} title={c.openCall} className="underline-offset-4 hover:text-foreground hover:underline">
          {day(example.observed_at)}
        </Link>
        {total > 1 ? (
          <span className="ml-auto inline-flex items-center gap-0.5 tabular-nums">
            <IconAction label={p.coachPrevious} disabled={index === 0} onClick={() => setIndex(index - 1)}>
              <ChevronLeft className="h-3.5 w-3.5" strokeWidth={1.5} />
            </IconAction>
            {index + 1}/{total}
            <IconAction label={p.coachNext} disabled={index === total - 1} onClick={() => setIndex(index + 1)}>
              <ChevronRight className="h-3.5 w-3.5" strokeWidth={1.5} />
            </IconAction>
          </span>
        ) : null}
      </div>
      {before.map((turn, i) => <Around key={`b${i}`} turn={turn} />)}
      <div className={cn("space-y-2 border-l-2 py-1 pl-3", frame)}>
        {example.turns.filter((turn) => !(turn.who === "rep" && isDraft(turn.quote, turn.said))).map((turn, i) => (
          <Bubble
            key={i}
            kind={turn.who === "client" ? "prospect" : "you"}
            caption={turn.who === "client" ? p.coachProspectSaid : p.coachYouSaid}
            said={turn.said}
            actions={turn.who === "rep" && suggestion.kind !== "worked" ? <AfterMark after={example.after} /> : undefined}
          >
            {turn.quote}
          </Bubble>
        ))}
      </div>
      {after.map((turn, i) => <Around key={`a${i}`} turn={turn} />)}
    </section>
  );
}

/** The open case: what it is and why it matters, the moment, and the answer to take into the playbook. */
function Detail({ suggestion, position, total, answers, decide, onMove, onClose }: {
  suggestion: Suggestion;
  position: number;
  total: number;
  answers: SuggestionAnswer[];
  decide: Decide;
  onMove: (step: -1 | 1) => void;
  /** Only when it opens over the list (narrow screens). */
  onClose?: () => void;
}) {
  const c = useCopy();
  const { t } = useLanguage();
  const p = t.product;
  const body = useRef<HTMLDivElement>(null);
  const [text, setText] = useState(suggestion.draft ?? "");
  useEffect(() => {
    setText(suggestion.draft ?? "");
    body.current?.scrollTo({ top: 0 });
  }, [suggestion.key, suggestion.draft]);
  const answerKind = suggestion.kind === "objection" || suggestion.kind === "question";
  const writable = answerKind || suggestion.kind === "opportunity";
  const context = contextOf(suggestion);
  // Whose words the draft is, only when it is not the rep already named over the call above (a value is shown once).
  const said = suggestion.draft_from === "colleague" ? suggestion.examples.find((e) => e.after === "advanced")?.rep || suggestion.reps[0] || "" : "";
  const colleague = said && said !== suggestion.examples[0]?.rep ? said : "";
  const complete = useMutation({
    mutationFn: (avoid?: string) => suggestionsApi.draft(suggestion.key, avoid),
    onSuccess: ({ text: written }) => (written ? setText(written) : toast(c.draftNone)),
    onError: () => toast(c.draftNone),
  });
  const busy = decide.accepting || decide.dismissing === suggestion.key || complete.isPending;
  const add = useCallback(() => {
    if (!busy && text.trim()) decide.accept(suggestion, text.trim());
  }, [busy, text, decide, suggestion]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
        event.preventDefault();
        add();
        return;
      }
      const field = event.target instanceof HTMLElement && event.target.closest("input, textarea, [contenteditable=true], [role=menu]");
      if (field || event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        onMove(event.key === "ArrowDown" ? 1 : -1);
      } else if (event.key === "Escape" && onClose) {
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onMove, onClose, add]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex items-center justify-between gap-2 px-6 pb-1 pt-4">
        <span className="text-[12.5px] tabular-nums text-muted-foreground">{c.position.replace("{n}", String(position + 1)).replace("{total}", String(total))}</span>
        <span className="flex items-center gap-0.5">
          <IconAction label={p.coachPrevious} disabled={position === 0} onClick={() => onMove(-1)}>
            <ChevronUp className="h-4 w-4" strokeWidth={1.5} />
          </IconAction>
          <IconAction label={p.coachNext} disabled={position >= total - 1} onClick={() => onMove(1)}>
            <ChevronDown className="h-4 w-4" strokeWidth={1.5} />
          </IconAction>
          {onClose ? (
            <IconAction label={p.coachClose} onClick={onClose}>
              <X className="h-4 w-4" strokeWidth={1.5} />
            </IconAction>
          ) : null}
        </span>
      </header>
      <div key={suggestion.key} ref={body} className={cn("app-scroll min-h-0 flex-1 space-y-6 overflow-y-auto overscroll-contain px-6 pb-6", THEME_TOKENS.motion.fadeIn)}>
        <div className="space-y-2">
          <p className="flex items-center gap-1.5 text-[12.5px] text-muted-foreground">
            <span aria-hidden className={cn("h-2 w-2 rounded-full", DOT[suggestion.kind])} />
            {[c.kinds[suggestion.kind], suggestion.motion_label, suggestion.count > 1 ? c.calls.replace("{count}", String(suggestion.count)) : null].filter(Boolean).join(" · ")}
          </p>
          <h3 className="text-[20px] font-semibold leading-snug tracking-[-0.01em] text-foreground">{suggestion.title}</h3>
          {context ? <p className="max-w-[62ch] text-[14.5px] leading-relaxed text-foreground/80">{context}</p> : null}
        </div>
        <Moment suggestion={suggestion} />
        <section className="space-y-1.5">
          {colleague ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <span tabIndex={0} className="inline-flex items-center gap-1 text-[12.5px] text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                  <Check aria-hidden className="h-3 w-3 text-success" strokeWidth={2} />
                  {colleague}
                  <span className="sr-only">{c.fromColleague.replace("{name}", colleague)}</span>
                </span>
              </TooltipTrigger>
              <TooltipContent side="top">{c.fromColleague.replace("{name}", colleague)}</TooltipContent>
            </Tooltip>
          ) : null}
          <label className="ml-auto flex max-w-[94%] items-start gap-2 rounded-2xl rounded-br-md border border-success/25 bg-success/10 px-3.5 py-2.5 focus-within:ring-1 focus-within:ring-success/40">
            <Lightbulb aria-hidden className="mt-1 h-3.5 w-3.5 shrink-0 text-success" strokeWidth={1.75} />
            <span className="sr-only">{c.draftLabel}</span>
            <textarea
              value={text}
              rows={Math.min(8, Math.max(3, Math.ceil(text.length / 60)))}
              placeholder={complete.isPending ? c.completing : c.draftPlaceholder}
              maxLength={1200}
              disabled={busy}
              onChange={(event) => setText(event.target.value)}
              className={cn(
                "min-w-0 flex-1 resize-none bg-transparent text-[14.5px] font-medium leading-snug text-foreground placeholder:font-normal placeholder:text-muted-foreground focus:outline-none",
                complete.isPending && "ask-shimmer",
              )}
            />
          </label>
          {writable ? (
            <div className="flex justify-end">
              {text.trim() ? (
                <IconAction label={c.regenerate} pending={complete.isPending} disabled={busy} onClick={() => complete.mutate(text.trim())}>
                  <RotateCw className="h-3.5 w-3.5" strokeWidth={1.5} />
                </IconAction>
              ) : (
                <Button type="button" variant="quiet" size="text" disabled={busy} onClick={() => complete.mutate(undefined)}>
                  {complete.isPending ? <VocifySpinner size={12} /> : null}
                  {c.complete}
                </Button>
              )}
            </div>
          ) : null}
        </section>
      </div>
      <footer className="flex items-center justify-between gap-3 border-t border-border/60 px-6 py-3.5">
        <DismissMenu answers={answers} busy={decide.dismissing === suggestion.key} onDismiss={(reason, coveredBy) => decide.dismiss(suggestion.key, reason, coveredBy)} />
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="inline-flex">
              <Button type="button" size="sm" disabled={busy || !text.trim()} onClick={add}>
                {decide.accepting ? <VocifySpinner size={12} /> : <Check aria-hidden strokeWidth={1.75} />}
                {c.addToPlaybook}
              </Button>
            </span>
          </TooltipTrigger>
          <TooltipContent side="top">
            {(answerKind ? c.addAnswer : c.addConduct).replace("{type}", suggestion.motion_label)}
            <kbd className="ml-1.5 font-sans text-muted-foreground">⌘↵</kbd>
          </TooltipContent>
        </Tooltip>
      </footer>
    </div>
  );
}

/** One line of the list: the title, what it is about in one line, ×N when it repeats. */
function ListRow({ suggestion, selected, onOpen }: { suggestion: Suggestion; selected: boolean; onOpen: () => void }) {
  const context = contextOf(suggestion);
  const row = useRef<HTMLButtonElement>(null);
  // Moving with ↑/↓ keeps the open one in sight in the list.
  useEffect(() => {
    if (selected) row.current?.scrollIntoView({ block: "nearest" });
  }, [selected]);
  return (
    <li>
      <button
        ref={row}
        type="button"
        aria-current={selected || undefined}
        onClick={onOpen}
        className={cn(
          "flex w-full items-start gap-2 rounded-xl px-3 py-2.5 text-left transition-colors motion-reduce:transition-none",
          selected ? "bg-secondary" : "hover:bg-secondary/60",
        )}
      >
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[14px] font-medium text-foreground">{suggestion.title}</span>
          {context ? <span className="mt-0.5 line-clamp-1 text-[12.5px] text-muted-foreground">{context}</span> : null}
        </span>
        {suggestion.count > 1 ? <span className="shrink-0 pt-0.5 text-[12px] tabular-nums text-foreground/70">×{suggestion.count}</span> : null}
      </button>
    </li>
  );
}

export type SuggestionsInboxViewProps = {
  body: SuggestionsBody;
  onDone: (body: SuggestionsBody) => void;
  /** A suggestion to open on arrival (Equipo's «Lo que pide atención» links to one). */
  initialKey?: string | null;
  /** Back to the playbook: the inbox's own header carries the way out. */
  onBack?: () => void;
};

/**
 * «Sugerencias»: what the team's calls taught, as an inbox the head of sales works through. On the left the cases
 * grouped by kind, each group folding, with how far they are; on the right the open one, always shown. Deciding one
 * opens the next; the page itself never scrolls, only the list and the case do.
 */
export function SuggestionsInboxView({ body, onDone, initialKey = null, onBack }: SuggestionsInboxViewProps) {
  const c = useCopy();
  const back = useLanguage().t.product.pb2.improve.back;
  const split = useSplit();
  const [folded, setFolded] = useState<Set<SuggestionKind>>(new Set());
  const groups = KINDS.map((kind) => ({ kind, items: body.suggestions.filter((s) => s.kind === kind) })).filter((g) => g.items.length);
  // The order ↑/↓ walk in: the groups as shown, the folded ones left out.
  const order = groups.flatMap((g) => (folded.has(g.kind) ? [] : g.items));
  const [openKey, setOpenKey] = useState<string | null>(() =>
    body.suggestions.some((s) => s.key === initialKey) ? initialKey : split ? order[0]?.key ?? null : null,
  );
  const openIndex = order.findIndex((s) => s.key === openKey);
  const open = body.suggestions.find((s) => s.key === openKey) ?? null;
  const waiting = body.suggestions.length;
  const decidedCount = body.decided ?? 0;
  const done = decidedCount + waiting ? decidedCount / (decidedCount + waiting) : 0;

  const decide = useDecide((next) => {
    // The next one in line takes the decided one's place, so the list is worked through without looking for it.
    if (openKey && !next.suggestions.some((s) => s.key === openKey)) {
      const left = KINDS.flatMap((kind) => (folded.has(kind) ? [] : next.suggestions.filter((s) => s.kind === kind)));
      setOpenKey(left[Math.min(Math.max(openIndex, 0), left.length - 1)]?.key ?? null);
    }
    onDone(next);
  });
  const move = useCallback(
    (step: -1 | 1) => {
      const next = order[Math.min(Math.max(openIndex + step, 0), order.length - 1)];
      if (next) setOpenKey(next.key);
    },
    [openIndex, order],
  );
  const close = useCallback(() => setOpenKey(null), []);
  const toggle = (kind: SuggestionKind) =>
    setFolded((now) => {
      const next = new Set(now);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });

  if (!waiting) {
    return (
      <div className={cn(card, "flex flex-col items-center gap-2 px-6 py-14 text-center")}>
        <GraduationCap aria-hidden className="h-6 w-6 text-success" strokeWidth={1.5} />
        <p className="text-[15px] font-medium text-foreground">{c.emptyTitle}</p>
        <p className="max-w-sm text-[13px] text-muted-foreground">{decidedCount ? c.allDone.replace("{count}", String(decidedCount)) : c.emptyLine}</p>
      </div>
    );
  }

  const list = (
    <div className="flex h-full min-h-0 flex-col">
      <div className="space-y-2 border-b border-border/60 px-2 pb-3 pt-1">
        <div className="flex items-center gap-1">
          {onBack ? (
            <IconAction label={back} onClick={onBack}>
              <ArrowLeft className="h-4 w-4" strokeWidth={1.5} />
            </IconAction>
          ) : null}
          <h2 className="text-[15px] font-semibold text-foreground">{c.title}</h2>
          {decidedCount ? (
            <span className="ml-auto pr-2 text-[12.5px] tabular-nums text-muted-foreground">{c.progress.replace("{done}", String(decidedCount)).replace("{total}", String(decidedCount + waiting))}</span>
          ) : (
            <span className="ml-auto pr-2 text-[12.5px] tabular-nums text-muted-foreground">{waiting}</span>
          )}
        </div>
        {decidedCount ? (
          <div className="mx-2 h-1 overflow-hidden rounded-full bg-secondary" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(done * 100)} aria-label={c.title}>
            <div className="h-full rounded-full bg-success transition-[width] duration-500 motion-reduce:transition-none" style={{ width: `${Math.round(done * 100)}%` }} />
          </div>
        ) : null}
      </div>
      <div className="app-scroll min-h-0 flex-1 overflow-y-auto overscroll-contain px-2 py-2">
        {groups.map((group) => (
          <section key={group.kind} className="pb-1">
            <button
              type="button"
              aria-expanded={!folded.has(group.kind)}
              onClick={() => toggle(group.kind)}
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-[12.5px] font-medium text-muted-foreground hover:text-foreground"
            >
              <span aria-hidden className={cn("h-2 w-2 rounded-full", DOT[group.kind])} />
              {c.kindsMany[group.kind]}
              <span className="tabular-nums">{group.items.length}</span>
              <ChevronDown aria-hidden className={cn("ml-auto h-3.5 w-3.5 transition-transform motion-reduce:transition-none", folded.has(group.kind) && "-rotate-90")} strokeWidth={1.5} />
            </button>
            {folded.has(group.kind) ? null : (
              <ul className="space-y-0.5">
                {group.items.map((suggestion) => (
                  <ListRow key={suggestion.key} suggestion={suggestion} selected={suggestion.key === openKey} onOpen={() => setOpenKey(suggestion.key)} />
                ))}
              </ul>
            )}
          </section>
        ))}
      </div>
    </div>
  );

  const detail = open ? (
    <Detail
      suggestion={open}
      position={Math.max(openIndex, 0)}
      total={order.length}
      answers={body.answers[open.motion] ?? []}
      decide={decide}
      onMove={move}
      onClose={split ? undefined : close}
    />
  ) : null;

  if (split) {
    return (
      <section className="grid h-[calc(100vh-11rem)] min-h-[560px] grid-cols-[minmax(280px,360px)_1fr] overflow-hidden">
        <div className="min-h-0 border-r border-border/60 pr-2">{list}</div>
        <div className="min-h-0">
          {detail ?? <p className="px-6 py-10 text-[13.5px] text-muted-foreground">{c.pickOne}</p>}
        </div>
      </section>
    );
  }
  return (
    <>
      <section className="h-[calc(100vh-11rem)] min-h-[480px] overflow-hidden">{list}</section>
      {detail ? (
        <Sheet open modal={false} onOpenChange={(next) => !next && close()}>
          <SheetPortal>
            <SheetPrimitive.Content
              aria-label={open?.title}
              onInteractOutside={(event) => event.preventDefault()}
              className="fixed inset-y-0 right-0 z-30 flex h-full w-[520px] max-w-full flex-col border-l border-border/70 bg-card p-0 shadow-lg outline-none data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right motion-reduce:animate-none"
            >
              <SheetPrimitive.Title className="sr-only">{open?.title}</SheetPrimitive.Title>
              {detail}
            </SheetPrimitive.Content>
          </SheetPortal>
        </Sheet>
      ) : null}
    </>
  );
}

/** The inbox wired to the company's suggestions; `?open=<key>` opens one on arrival. */
export function SuggestionsInbox({ onChanged, onBack }: { onChanged?: () => void; onBack?: () => void }) {
  const c = useCopy();
  const queryClient = useQueryClient();
  const [params] = useSearchParams();
  const query = useQuery({ queryKey: SUGGESTIONS_QUERY, queryFn: suggestionsApi.list, staleTime: 60_000 });
  if (query.isPending) return <Skeleton className="h-[calc(100vh-15rem)] min-h-[560px] w-full rounded-2xl" />;
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
      initialKey={params.get("open")}
      onBack={onBack}
      onDone={(body) => {
        queryClient.setQueryData(SUGGESTIONS_QUERY, body);
        onChanged?.();
      }}
    />
  );
}
