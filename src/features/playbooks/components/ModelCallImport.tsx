import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, FileText } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { errorCode, playbooksApi } from "@/features/playbooks/api";
import { assistantApi, type ModelProposal, type ProposeResult } from "@/features/playbooks/assistantApi";
import { ModelCallProposalsView } from "@/features/playbooks/components/ModelCallProposals";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

type Tab = "paste" | "pick";
type Scope = "whole" | "moment";

const field = cn(
  THEME_TOKENS.radius.control,
  "block w-full resize-y border border-border bg-background px-3 py-2.5 text-[14.5px] leading-relaxed text-foreground placeholder:text-muted-foreground/70 focus:outline-none focus:ring-1 focus:ring-beige/40",
);

/**
 * "Una llamada modelo": the Head of Sales gives a call where it went well (pasted, from a text file or one of the
 * company's own calls), Vocify reads it and proposes what to keep (a real example for a step, how an objection was
 * answered and in which situation), each with the passage it comes from. The call itself is never stored: only what
 * the Head of Sales chooses reaches the draft. A side sheet over the playbook, so there is always a way back.
 */
export function ModelCallImport({
  open,
  onOpenChange,
  motionKey,
  typeName,
  onApplied,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  motionKey: string;
  typeName: string;
  /** The draft changed: the playbook is read again. */
  onApplied: () => void;
}) {
  const { t, language } = useLanguage();
  const c = t.product.pb2.improve;
  const picker = useRef<HTMLInputElement>(null);
  const [tab, setTab] = useState<Tab>("paste");
  const [transcript, setTranscript] = useState("");
  const [memoId, setMemoId] = useState<string | null>(null);
  const [scope, setScope] = useState<Scope>("whole");
  const [moment, setMoment] = useState("");
  const [note, setNote] = useState("");
  const [reading, setReading] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [result, setResult] = useState<ProposeResult | null>(null);
  // What the Head of Sales decided about each proposal.
  const [chosen, setChosen] = useState<Record<string, boolean>>({});
  const [texts, setTexts] = useState<Record<string, string>>({});
  const [skipped, setSkipped] = useState<Record<string, string>>({});
  const [swapped, setSwapped] = useState(false);
  const [applying, setApplying] = useState(false);

  // The names of the steps, so a proposal says "para el paso «Apertura»" and not "paso 1".
  const editor = useQuery({
    queryKey: ["playbooks", "editor", motionKey],
    queryFn: () => playbooksApi.editor(motionKey),
    enabled: open && Boolean(result),
    retry: false,
  });
  const stepLabel = (index: number) => editor.data?.steps[index - 1]?.label ?? "";
  const objectionLabel = (proposal: ModelProposal) =>
    proposal.category === "custom"
      ? (proposal.label ?? "")
      : (t.product.playbookObjectionCategories[proposal.category as keyof typeof t.product.playbookObjectionCategories] ?? proposal.category ?? "");

  const calls = useQuery({
    queryKey: ["playbook-assistant", "recent-calls"],
    queryFn: assistantApi.recentCalls,
    enabled: open && tab === "pick",
    retry: false,
    staleTime: 60_000,
  });

  const reset = () => {
    setResult(null);
    setProblem(null);
    setChosen({});
    setTexts({});
    setSkipped({});
    setSwapped(false);
  };
  const message = (code: string | null) => (code && c.errors[code]) || c.errors.unknown;
  const ready = tab === "paste" ? transcript.trim().length > 0 : Boolean(memoId);

  const read = async () => {
    if (!ready || reading) return;
    setReading(true);
    setProblem(null);
    try {
      const body = {
        motion_key: motionKey,
        ...(tab === "paste" ? { transcript: transcript.trim() } : { memo_id: memoId ?? undefined }),
        scope: scope === "moment" && moment.trim() ? ({ kind: "moment", text: moment.trim() } as const) : ({ kind: "whole" } as const),
        ...(note.trim() ? { note: note.trim() } : {}),
      };
      setResult(await assistantApi.proposeFromCall(body));
    } catch (error) {
      setProblem(message(errorCode(error)));
    } finally {
      setReading(false);
    }
  };

  const apply = async (only?: ModelProposal[]) => {
    if (!result) return;
    const picks =
      only ??
      result.proposals.filter((p) => chosen[p.id] !== false).map((p) => ({ ...p, text: texts[p.id] ?? p.text }));
    if (!picks.length) return;
    setApplying(true);
    setProblem(null);
    try {
      const done = await assistantApi.applyProposals(motionKey, picks);
      onApplied();
      const left = result.proposals.filter((p) => !done.applied.includes(p.id));
      setResult({ ...result, proposals: left });
      setSkipped(Object.fromEntries(done.skipped.map((item) => [item.id, item.code])));
      if (done.applied.length) toast.success(c.proposalsApplied);
      if (!done.skipped.length) {
        reset();
        onOpenChange(false);
      }
    } catch (error) {
      setProblem(message(errorCode(error)));
    } finally {
      setApplying(false);
    }
  };

  const view = result ? (
    <div className="space-y-4">
      <ModelCallProposalsView
        proposals={result.proposals}
        stepLabel={stepLabel}
        objectionLabel={objectionLabel}
        speakerWarning={result.speaker_warning}
        swapped={swapped}
        chosen={chosen}
        texts={texts}
        skipped={skipped}
        applying={applying}
        onToggle={(id, on) => setChosen((now) => ({ ...now, [id]: on }))}
        onText={(id, text) => setTexts((now) => ({ ...now, [id]: text }))}
        onDiscard={(id) => setResult({ ...result, proposals: result.proposals.filter((p) => p.id !== id) })}
        onSwap={() => setSwapped((now) => !now)}
        onApply={() => void apply()}
        onOwn={(id, name) => {
          const proposal = result.proposals.find((p) => p.id === id);
          if (proposal) void apply([{ ...proposal, text: texts[id] ?? proposal.text, as_custom: name }]);
        }}
      />
      <Button type="button" variant="quiet" size="text" onClick={reset}>
        {c.modelBack}
      </Button>
    </div>
  ) : (
    <div className="space-y-5">
      <Segmented<Tab>
        aria-label={c.modelTitle}
        value={tab}
        onValueChange={setTab}
        options={[
          { value: "paste", label: c.modelPaste },
          { value: "pick", label: c.modelPick },
        ]}
      />
      {tab === "paste" ? (
        <div className="space-y-2">
          <textarea
            value={transcript}
            rows={9}
            readOnly={reading}
            placeholder={c.modelTranscriptPlaceholder}
            aria-label={c.modelTranscriptPlaceholder}
            className={field}
            onChange={(event) => setTranscript(event.target.value)}
          />
          <Button type="button" variant="quiet" size="text" disabled={reading} onClick={() => picker.current?.click()}>
            <FileText aria-hidden strokeWidth={1.5} />
            {c.modelFromFile}
          </Button>
          <input
            ref={picker}
            type="file"
            className="sr-only"
            tabIndex={-1}
            accept=".txt,.md,text/plain"
            onChange={async (event) => {
              const picked = event.target.files?.[0];
              event.target.value = "";
              if (picked) setTranscript(await picked.text());
            }}
          />
        </div>
      ) : (
        <div className="space-y-1">
          {calls.isLoading ? (
            <div className="space-y-2" aria-busy="true">
              {[0, 1, 2].map((key) => (
                <Skeleton key={key} className="h-14 w-full motion-reduce:animate-none" />
              ))}
            </div>
          ) : calls.data?.calls.length ? (
            <ul className="-mx-2 space-y-0.5">
              {calls.data.calls.map((call) => (
                <li key={call.id}>
                  <button
                    type="button"
                    aria-pressed={memoId === call.id}
                    onClick={() => setMemoId(call.id)}
                    className={cn("flex w-full items-start gap-3 rounded-lg px-2 py-2.5 text-left", THEME_TOKENS.interaction.rowHover, "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring")}
                  >
                    <span className="w-16 shrink-0 text-xs text-muted-foreground">
                      {call.created_at ? new Date(call.created_at).toLocaleDateString(language === "EN" ? "en-GB" : "es-ES", { day: "numeric", month: "short" }) : ""}
                    </span>
                    <span className="min-w-0 flex-1 text-[14.5px] leading-snug text-foreground">{call.summary || "—"}</span>
                    {memoId === call.id ? <Check aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-beige" strokeWidth={2} /> : <span className="w-4" />}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className={THEME_TOKENS.typography.body}>{calls.isError ? c.loadFailed : c.modelNoCalls}</p>
          )}
        </div>
      )}
      <div className="space-y-2">
        <Segmented<Scope>
          aria-label={c.modelTitle}
          value={scope}
          onValueChange={setScope}
          options={[
            { value: "whole", label: c.modelWhole },
            { value: "moment", label: c.modelMoment },
          ]}
        />
        {scope === "moment" ? (
          <textarea value={moment} rows={3} placeholder={c.modelMomentPlaceholder} aria-label={c.modelMomentPlaceholder} className={field} onChange={(event) => setMoment(event.target.value)} />
        ) : null}
        <textarea value={note} rows={2} placeholder={c.modelNotePlaceholder} aria-label={c.modelNotePlaceholder} className={field} onChange={(event) => setNote(event.target.value)} />
      </div>
      <div className="flex items-center gap-3">
        <Button type="button" disabled={!ready || reading} onClick={() => void read()}>
          {reading ? <VocifySpinner size={12} tone="onFill" /> : null}
          {reading ? c.modelReading : c.modelRead}
        </Button>
      </div>
    </div>
  );

  return (
    <Sheet
      open={open}
      onOpenChange={(next) => {
        if (!next && !applying) onOpenChange(false);
      }}
    >
      <SheetContent side="right" className="w-full space-y-5 overflow-y-auto sm:max-w-xl">
        <SheetHeader className="space-y-1 text-left">
          <SheetTitle className={THEME_TOKENS.typography.panelTitle}>{c.modelTitle}</SheetTitle>
          <SheetDescription className="text-[13px] leading-snug text-muted-foreground">
            {c.modelFor.replace("{type}", typeName)}. {c.modelLead}
          </SheetDescription>
        </SheetHeader>
        {view}
        {problem ? (
          <p className="text-sm text-destructive" role="alert">
            {problem}
          </p>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
