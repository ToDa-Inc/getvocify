import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import * as SheetPrimitive from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Check, ChevronDown, ChevronLeft, ChevronRight, ChevronUp, GraduationCap, Lightbulb, X } from "lucide-react";
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
import { Pagination, PaginationContent, PaginationItem } from "@/components/ui/pagination";
import { Segmented } from "@/components/ui/segmented";
import { Sheet, SheetPortal } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { Bubble } from "@/features/coaching/rep/OccurrencePager";
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
import { PAGINATION } from "@/shared/lib/constants";

const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card}`;
const KINDS: readonly SuggestionKind[] = ["objection", "question", "worked", "opportunity"];
// One small dot per kind, so the list reads at a glance: what pushes back, what they ask, what worked, what opened.
const DOT: Record<SuggestionKind, string> = {
  objection: "bg-warning",
  question: "bg-foreground/40",
  worked: "bg-success",
  opportunity: "bg-beige",
};
const PAGE = PAGINATION.DEFAULT_PAGE_SIZE;

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

/** What a suggestion is about, in one line: the reading's context, else how the call ended. */
function contextOf(suggestion: Suggestion): string | null {
  return suggestion.why || suggestion.examples.find((e) => e.summary)?.summary || null;
}

/** Set it aside with a reason in one tap; «Ya cubierta» with the answer that covers it. */
function DismissMenu({ answers, busy, onDismiss, trigger }: {
  answers: SuggestionAnswer[];
  busy: boolean;
  onDismiss: (reason: DismissReason, coveredBy?: string) => void;
  trigger: "icon" | "button";
}) {
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
      {trigger === "icon" ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <DropdownMenuTrigger asChild>
              <button type="button" aria-label={c.dismiss} disabled={busy} className={cn(THEME_TOKENS.interaction.iconButton, "h-7 w-7")}>
                {busy ? <VocifySpinner size={12} /> : <X aria-hidden className="h-3.5 w-3.5" strokeWidth={1.5} />}
              </button>
            </DropdownMenuTrigger>
          </TooltipTrigger>
          <TooltipContent side="top">{c.dismiss}</TooltipContent>
        </Tooltip>
      ) : (
        <DropdownMenuTrigger asChild>
          <Button type="button" variant="quiet" size="sm" disabled={busy}>
            {busy ? <VocifySpinner size={12} /> : null}
            {c.dismiss}
            <ChevronDown aria-hidden strokeWidth={1.5} />
          </Button>
        </DropdownMenuTrigger>
      )}
      <DropdownMenuContent align={trigger === "icon" ? "end" : "start"} className="w-72">
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

/** The decisions on a suggestion, shared by the list (dismiss) and the panel (dismiss, add). */
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

/** One line of the list: the kind's dot, the title and what it is about, how often and when; the way out on hover. */
function ListRow({ suggestion, selected, answers, dismissing, onOpen, onDismiss }: {
  suggestion: Suggestion;
  selected: boolean;
  answers: SuggestionAnswer[];
  dismissing: boolean;
  onOpen: () => void;
  onDismiss: (reason: DismissReason, coveredBy?: string) => void;
}) {
  const c = useCopy();
  const day = useDay();
  const context = contextOf(suggestion);
  const row = useRef<HTMLLIElement>(null);
  // Moving through the panel with ↑/↓ keeps the open one in sight in the list.
  useEffect(() => {
    if (selected) row.current?.scrollIntoView({ block: "nearest" });
  }, [selected]);
  return (
    <li ref={row} className={cn("group flex items-center gap-2 border-t border-border/50 pr-2 first:border-t-0", selected ? "bg-secondary/70" : THEME_TOKENS.interaction.rowHover)}>
      <button type="button" aria-current={selected || undefined} onClick={onOpen} className="flex min-w-0 flex-1 items-center gap-3 py-3 pl-4 text-left md:pl-5">
        <span aria-hidden className={cn("h-2 w-2 shrink-0 rounded-full", DOT[suggestion.kind])} />
        <span className="sr-only">{c.kinds[suggestion.kind]}</span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[14.5px] font-medium text-foreground">{suggestion.title}</span>
          {context ? <span className="block truncate text-[13px] text-muted-foreground">{context}</span> : null}
        </span>
        {suggestion.count > 1 ? <span className="shrink-0 text-[12.5px] tabular-nums text-foreground/70">×{suggestion.count}</span> : null}
        <span className="w-14 shrink-0 text-right text-[12.5px] tabular-nums text-muted-foreground">{day(suggestion.last_at)}</span>
      </button>
      <span className={cn("shrink-0 transition-opacity motion-reduce:transition-none", dismissing ? "opacity-100" : "opacity-0 focus-within:opacity-100 group-hover:opacity-100")}>
        <DismissMenu trigger="icon" answers={answers} busy={dismissing} onDismiss={onDismiss} />
      </span>
    </li>
  );
}

/** The call a suggestion came from: who and when once (the date opens the call), and the exchange as it happened. */
function Moment({ suggestion }: { suggestion: Suggestion }) {
  const c = useCopy();
  const { t } = useLanguage();
  const p = t.product;
  const day = useDay();
  const [index, setIndex] = useState(0);
  useEffect(() => setIndex(0), [suggestion.key]);
  const example = suggestion.examples[Math.min(index, suggestion.examples.length - 1)];
  if (!example) return null;
  // A colleague's words that worked are the draft below: shown there once, not again as their bubble.
  const isDraft = (quote: string, said: string | null) =>
    suggestion.draft_from === "colleague" && !!suggestion.draft && (suggestion.draft === quote || suggestion.draft === said);
  const total = suggestion.examples.length;
  return (
    <section className="space-y-2.5">
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
      {example.turns.filter((turn) => !(turn.who === "rep" && isDraft(turn.quote, turn.said))).map((turn, i) => (
        <Bubble key={i} kind={turn.who === "client" ? "prospect" : "you"} caption={turn.who === "client" ? p.coachProspectSaid : p.coachYouSaid} said={turn.said}>
          {turn.quote}
        </Bubble>
      ))}
    </section>
  );
}

/** The open suggestion, on the right like Coaching's call: what it is and why it matters, the call it came from, and the
 * answer to take into the playbook. ↑/↓ move through the list, Esc closes, ⌘↵ adds. */
function Panel({ suggestion, position, total, answers, decide, onMove, onClose }: {
  suggestion: Suggestion;
  position: number;
  total: number;
  answers: SuggestionAnswer[];
  decide: Decide;
  onMove: (step: -1 | 1) => void;
  onClose: () => void;
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
  const context = contextOf(suggestion);
  // Whose words the draft is, only when it is not the rep already named over the call above (a value is shown once).
  const said = suggestion.draft_from === "colleague" ? suggestion.examples.find((e) => e.after === "advanced")?.rep || suggestion.reps[0] || "" : "";
  const colleague = said && said !== suggestion.examples[0]?.rep ? said : "";
  const complete = useMutation({
    mutationFn: () => suggestionsApi.draft(suggestion.key),
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
      } else if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onMove, onClose, add]);

  return (
    <Sheet open modal={false} onOpenChange={(next) => !next && onClose()}>
      <SheetPortal>
        <SheetPrimitive.Content
          aria-label={suggestion.title}
          onInteractOutside={(event) => event.preventDefault()}
          className="fixed inset-y-0 right-0 z-30 flex h-full w-[520px] max-w-full flex-col border-l border-border/70 bg-card p-0 shadow-lg outline-none data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right data-[state=closed]:duration-300 data-[state=open]:duration-500 motion-reduce:animate-none"
        >
          <SheetPrimitive.Title className="sr-only">{suggestion.title}</SheetPrimitive.Title>
          <header className="flex items-center justify-between gap-2 px-6 pb-1 pt-4">
            <span className="text-[12.5px] tabular-nums text-muted-foreground">{c.position.replace("{n}", String(position + 1)).replace("{total}", String(total))}</span>
            <span className="flex items-center gap-0.5">
              <IconAction label={p.coachPrevious} disabled={position === 0} onClick={() => onMove(-1)}>
                <ChevronUp className="h-4 w-4" strokeWidth={1.5} />
              </IconAction>
              <IconAction label={p.coachNext} disabled={position >= total - 1} onClick={() => onMove(1)}>
                <ChevronDown className="h-4 w-4" strokeWidth={1.5} />
              </IconAction>
              <IconAction label={p.coachClose} onClick={onClose}>
                <X className="h-4 w-4" strokeWidth={1.5} />
              </IconAction>
            </span>
          </header>
          <div key={suggestion.key} ref={body} className={cn("app-scroll min-h-0 flex-1 space-y-6 overflow-y-auto overscroll-contain px-6 pb-6", THEME_TOKENS.motion.fadeIn)}>
            <div className="space-y-2">
              <p className="flex items-center gap-1.5 text-[12.5px] text-muted-foreground">
                <span aria-hidden className={cn("h-2 w-2 rounded-full", DOT[suggestion.kind])} />
                {[c.kinds[suggestion.kind], suggestion.motion_label, suggestion.count > 1 ? c.calls.replace("{count}", String(suggestion.count)) : null].filter(Boolean).join(" · ")}
              </p>
              <h3 className="text-[20px] font-semibold leading-snug tracking-[-0.01em] text-foreground">{suggestion.title}</h3>
              {context ? <p className="text-[14.5px] leading-relaxed text-foreground/80">{context}</p> : null}
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
              <label className="flex items-start gap-2 rounded-2xl rounded-br-md border border-success/25 bg-success/10 px-3.5 py-2.5 focus-within:ring-1 focus-within:ring-success/40">
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
              {answerKind && !text.trim() ? (
                <div className="flex justify-end">
                  <Button type="button" variant="quiet" size="text" disabled={busy} onClick={() => complete.mutate()}>
                    {complete.isPending ? <VocifySpinner size={12} /> : null}
                    {c.complete}
                  </Button>
                </div>
              ) : null}
            </section>
          </div>
          <footer className="flex items-center justify-between gap-3 border-t border-border/60 px-6 py-3.5">
            <DismissMenu trigger="button" answers={answers} busy={decide.dismissing === suggestion.key} onDismiss={(reason, coveredBy) => decide.dismiss(suggestion.key, reason, coveredBy)} />
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
        </SheetPrimitive.Content>
      </SheetPortal>
    </Sheet>
  );
}

export type SuggestionsInboxViewProps = {
  body: SuggestionsBody;
  onDone: (body: SuggestionsBody) => void;
};

/**
 * «Sugerencias»: what the team's calls taught, best first, as a list the head of sales works through. One line each; the
 * open one on the right, decided with their own words or set aside with a reason Vocify learns from, and the next one
 * takes its place.
 */
export function SuggestionsInboxView({ body, onDone }: SuggestionsInboxViewProps) {
  const c = useCopy();
  const { t } = useLanguage();
  const pages = t.product.interactions;
  const [kind, setKind] = useState<SuggestionKind | "all">("all");
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const present = KINDS.filter((k) => body.suggestions.some((s) => s.kind === k));
  const shown = body.suggestions.filter((s) => kind === "all" || s.kind === kind);
  const total = Math.max(1, Math.ceil(shown.length / PAGE));
  const current = Math.min(page, total - 1);
  const visible = shown.slice(current * PAGE, current * PAGE + PAGE);
  const openIndex = shown.findIndex((s) => s.key === openKey);
  const open = openIndex >= 0 ? shown[openIndex] : null;
  const count = (k: SuggestionKind | "all") => (k === "all" ? body.suggestions.length : body.suggestions.filter((s) => s.kind === k).length);

  const decide = useDecide((next) => {
    // The next one in line takes the decided one's place, so the list is worked through without looking for it.
    if (openKey && !next.suggestions.some((s) => s.key === openKey)) {
      const left = next.suggestions.filter((s) => kind === "all" || s.kind === kind);
      setOpenKey(left[Math.min(Math.max(openIndex, 0), left.length - 1)]?.key ?? null);
    }
    onDone(next);
  });
  const move = useCallback(
    (step: -1 | 1) => {
      const index = Math.min(Math.max(openIndex + step, 0), shown.length - 1);
      const next = shown[index];
      if (!next) return;
      setOpenKey(next.key);
      setPage(Math.floor(index / PAGE));
    },
    [openIndex, shown],
  );
  const close = useCallback(() => setOpenKey(null), []);

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
              setKind(next);
              setPage(0);
              setOpenKey(null);
            }}
            options={[
              { value: "all", label: <span>{c.all} <span className="tabular-nums text-muted-foreground">{count("all")}</span></span> },
              ...present.map((k) => ({
                value: k,
                label: (
                  <span className="inline-flex items-center gap-1.5">
                    <span aria-hidden className={cn("h-1.5 w-1.5 rounded-full", DOT[k])} />
                    {c.kindsMany[k]} <span className="tabular-nums text-muted-foreground">{count(k)}</span>
                  </span>
                ),
              })),
            ]}
          />
        ) : null}
      </div>
      {shown.length ? (
        <ul className={cn(card, "overflow-hidden")}>
          {visible.map((suggestion) => (
            <ListRow
              key={suggestion.key}
              suggestion={suggestion}
              selected={suggestion.key === openKey}
              answers={body.answers[suggestion.motion] ?? []}
              dismissing={decide.dismissing === suggestion.key}
              onOpen={() => setOpenKey(suggestion.key)}
              onDismiss={(reason, coveredBy) => decide.dismiss(suggestion.key, reason, coveredBy)}
            />
          ))}
        </ul>
      ) : (
        <div className={cn(card, "flex flex-col items-center gap-2 px-6 py-12 text-center")}>
          <GraduationCap aria-hidden className="h-6 w-6 text-success" strokeWidth={1.5} />
          <p className="text-[15px] font-medium text-foreground">{c.emptyTitle}</p>
          <p className="max-w-sm text-[13px] text-muted-foreground">{c.emptyLine}</p>
        </div>
      )}
      {total > 1 ? (
        <Pagination aria-label={pages.pages}>
          <PaginationContent className="gap-3">
            <PaginationItem>
              <Button variant="outline" size="sm" disabled={current === 0} onClick={() => setPage(current - 1)}>
                <ChevronLeft aria-hidden />
                {pages.previous}
              </Button>
            </PaginationItem>
            <PaginationItem aria-current="page" className="text-[13px] tabular-nums text-muted-foreground">
              {pages.page.replace("{n}", String(current + 1))} / {total}
            </PaginationItem>
            <PaginationItem>
              <Button variant="outline" size="sm" disabled={current >= total - 1} onClick={() => setPage(current + 1)}>
                {pages.next}
                <ChevronRight aria-hidden />
              </Button>
            </PaginationItem>
          </PaginationContent>
        </Pagination>
      ) : null}
      {open ? (
        <Panel
          suggestion={open}
          position={openIndex}
          total={shown.length}
          answers={body.answers[open.motion] ?? []}
          decide={decide}
          onMove={move}
          onClose={close}
        />
      ) : null}
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
        <Skeleton className="ml-auto h-9 w-96 rounded-3xl" />
        <Skeleton className="h-80 w-full rounded-2xl" />
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
