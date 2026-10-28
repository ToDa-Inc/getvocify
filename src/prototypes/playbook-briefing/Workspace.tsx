// Prototype: one call type's playbook in three blocks, the minimum the live brain needs to decide well: 1. what we want
// to achieve (and the other endings that count), 2. how Vocify should help in this kind of conversation (ONE orientation
// paragraph, edited directly or changed by talking to Vocify), 3. the information it works with (the playbook's steps,
// qualification and objections, plus the company notes and imported documents), opened on the side and edited like the
// playbook. «Vocify» is a side chat: ask about the playbook or ask for a change, which comes as a proposal to apply.
// «Probar» is secondary: a situation or a real call; a wrong card goes to that chat and adjusts the same paragraph.
// Opened from the real Playbook funnel. Real playbook and model (local API); the goal and orientation live in this page.
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { ArrowUp, ChevronDown, ChevronRight, Clock, FileUp, ListOrdered, MessagesSquare, Pencil, PencilLine, PhoneCall, Play, Plus, ShieldQuestion, Smile, Sparkles, Target, X, type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { IconAction } from "@/components/ui/icon-action";
import { Input } from "@/components/ui/input";
import { Segmented } from "@/components/ui/segmented";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { blobBase64, playbooksApi, type EditorDoc, type FillSource, type PlaybookList } from "@/features/playbooks/api";
import { DocRow, ItemMenu, NumberMark, QuoteMark } from "@/features/playbooks/components/DocParts";
import { InlineTextarea } from "@/features/playbooks/components/InlineField";
import { WindowShell } from "@/features/playbooks/components/home/WindowShell";
import { itemBody, itemTitle } from "@/features/playbooks/styles";
import { customObjectionId, editorFromStructure, sourceKindForFile } from "@/lib/playbook-doc";
import { draftPayload, newStepKey } from "@/lib/playbook-editor";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

/** The prototype's local API (prototypes/playbook-briefing/local_api.py). */
const LOCAL_API = "http://localhost:8888/prototype/copilot";

type Area = "steps" | "info" | "answers" | "test" | "ai";
type Alternative = { label: string; when: string };
type Structure = {
  goal: string;
  alternatives: Alternative[];
  orientation: string;
  steps: { n: number; when: string }[];
  info: { n: number; evidence: string; not_evidence: string; essential: boolean }[];
  themes: { name: string; answers: number[] }[];
};
type Turn = { id: string; who: "you" | "them"; text: string; t: number };
type ReviewCall = { name: string; turns: Turn[]; shown: { visible_t: number; say: string }[] };
/** A change Vocify proposes, shown before it is applied. */
type Proposal = {
  summary: string;
  before?: string;
  after?: string;
  /** Playbook items that are new or reworded, as the playbook shows them. */
  items?: { title: string; body: string }[];
  apply: () => void | Promise<void>;
  state?: "applied" | "discarded";
};
/** One line of the chat with Vocify; a moment of «Probar» it is about, quoted above. */
type Message = { who: "user" | "vocify"; text: string; quote?: string; proposal?: Proposal };

const GOALS: Record<string, string> = {
  meeting_booked: "reunión con día y hora",
  proposal_and_close: "siguiente paso con fecha",
  demo_booked: "demo agendada",
  close_date: "fecha de decisión o firma",
};
const CHAT_HINTS = ["¿Qué le falta a este playbook?", "Que sea menos insistente", "Que profundice más antes de presentar"];
/** A few situations to try it in; a real call last, only when there is one. */
const TRIES: { key: string; label: string; icon: LucideIcon; scenario?: string }[] = [
  { key: "interesado", label: "Interesado", icon: Smile },
  { key: "esceptico", label: "Escéptico", icon: ShieldQuestion },
  { key: "sin_tiempo", label: "Sin tiempo", icon: Clock },
];

const post = async <T,>(path: string, body: object): Promise<T> => {
  const response = await fetch(`${LOCAL_API}/${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!response.ok) throw new Error(String(response.status));
  return response.json();
};
type Namer = (o: EditorDoc["objections"][number]) => string;
/** The playbook numbered as Vocify reads it to organise it: S steps, Q what to find out, R answers. */
const numbered = (doc: EditorDoc, answerName: Namer) =>
  [
    ...(doc.steps ?? []).map((s, i) => `S${i + 1}: ${s.label} | ${s.criterion ?? ""} | ${s.example ?? ""}`),
    ...(doc.qualification ?? []).map((q, i) => `Q${i + 1}: ${q.label} | ${q.good ?? ""}`),
    ...(doc.objections ?? []).map((o, i) => `R${i + 1}: ${answerName(o)} | ${o.guidance ?? ""}`),
  ].join("\n");
const payloadOf = (doc: EditorDoc) =>
  draftPayload(
    (doc.steps ?? []).map((s) => ({ ...s, key: s.step_id ?? s.label })) as never,
    (doc.objections ?? []) as never,
    (doc.qualification ?? []).map((q) => ({ ...q, key: q.criterion_id ?? q.label })) as never,
  );
const NO_ANSWERS: EditorDoc["objections"] = [];
const clock = (t: number) => `${Math.floor(t / 60)}:${String(Math.round(t % 60)).padStart(2, "0")}`;
const field = cn(
  THEME_TOKENS.radius.control,
  "block w-full resize-none border border-border bg-background px-3 py-2 text-[14px] leading-relaxed text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-beige/40",
);

/** A block of the page: its number and question, one line under it, and what it holds. */
function Block({ n, title, lead, action, children }: { n: number; title: string; lead?: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="space-y-2.5">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-semibold tabular-nums text-foreground">{n}</span>
        <div className="min-w-0 flex-1">
          <h2 className={THEME_TOKENS.typography.sectionTitle}>{title}</h2>
          {lead ? <p className="text-[13px] text-muted-foreground">{lead}</p> : null}
        </div>
        {action}
      </div>
      <div className="pl-9">{children}</div>
    </section>
  );
}

/** A change in the chat: what it was and what it would be, applied only when the manager says so. */
function ProposalBox({ proposal, onSettle }: { proposal: Proposal; onSettle: (state: "applied" | "discarded") => void }) {
  const [busy, setBusy] = useState(false);
  return (
    <div className="space-y-2 rounded-xl border border-border bg-card px-3.5 py-3">
      <p className="text-[12.5px] font-medium text-muted-foreground">{proposal.summary}</p>
      {proposal.before ? <p className="text-[13px] leading-relaxed text-muted-foreground line-through decoration-muted-foreground/40">{proposal.before}</p> : null}
      {proposal.after ? <p className="border-l-2 border-beige/60 pl-3 text-[14px] leading-relaxed text-foreground">{proposal.after}</p> : null}
      {proposal.items?.map((item) => (
        <div key={item.title} className="border-l-2 border-beige/60 pl-3">
          <p className="text-[14px] font-medium leading-snug text-foreground">{item.title}</p>
          {item.body ? <p className="text-[13.5px] leading-relaxed text-foreground/80">{item.body}</p> : null}
        </div>
      ))}
      {proposal.state ? (
        <p className="pt-0.5 text-[12.5px] text-muted-foreground">{proposal.state === "applied" ? "Aplicado" : "Descartado"}</p>
      ) : (
        <div className="flex gap-2 pt-1">
          <Button
            type="button"
            size="sm"
            disabled={busy}
            onClick={() => {
              setBusy(true);
              void Promise.resolve(proposal.apply())
                .then(() => onSettle("applied"))
                .catch(() => toast.error("No se pudo aplicar. Prueba otra vez."))
                .finally(() => setBusy(false));
            }}
          >
            {busy ? <VocifySpinner size={12} /> : null}
            Aplicar
          </Button>
          <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={() => onSettle("discarded")}>
            Descartar
          </Button>
        </div>
      )}
    </div>
  );
}

/** One suggestion of the call being tried, and what the manager thinks of it; a correction goes to the chat with Vocify. */
function Moment({ them, say, at, label, onCorrect }: { them: string; say: string; at: number; label: string; onCorrect: (feedback: string) => Promise<void> }) {
  const [mode, setMode] = useState<"idle" | "good" | "bad">("idle");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <li className="space-y-2 border-b border-border/50 py-3 last:border-b-0">
      <p className="text-[13px] leading-relaxed text-foreground/80">
        <span className="mr-1.5 text-xs tabular-nums text-muted-foreground">{clock(at)}</span>
        <span className="font-medium text-beige">{label}</span> «{them}»
      </p>
      <p className="rounded-lg bg-secondary/50 px-3 py-2 text-[14px] leading-snug text-foreground">{say}</p>
      {mode === "good" ? (
        <p className="text-[12.5px] text-muted-foreground">Anotado.</p>
      ) : mode === "bad" ? (
        <form
          className="flex items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!text.trim()) return;
            setBusy(true);
            void onCorrect(text.trim()).finally(() => {
              setBusy(false);
              setMode("idle");
              setText("");
            });
          }}
        >
          <Input autoFocus value={text} disabled={busy} onChange={(e) => setText(e.target.value)} placeholder="¿Qué debería haber hecho?" className="h-8 flex-1 text-[13px]" />
          <Button type="submit" size="sm" disabled={busy || !text.trim()}>
            {busy ? <VocifySpinner size={12} /> : null}
            Decírselo a Vocify
          </Button>
        </form>
      ) : (
        <div className="flex gap-1.5 text-[12.5px]">
          <button type="button" onClick={() => setMode("good")} className="rounded-full border border-border px-2.5 py-0.5 text-foreground/80 hover:border-foreground/40">
            Bien
          </button>
          <button type="button" onClick={() => setMode("bad")} className="rounded-full border border-border px-2.5 py-0.5 text-foreground/80 hover:border-foreground/40">
            No haría esto
          </button>
        </div>
      )}
    </li>
  );
}

export function Workspace({ motion }: { motion: string }) {
  const { t } = useLanguage();
  const says = t.product.pb2.objectionSays as Record<string, string>;
  const kinds = t.product.playbookObjectionCategories as Record<string, string>;
  /** What the prospect says, as the playbook shows it: the company's name for it, their words, or the usual phrase. */
  const answerName: Namer = (o) =>
    o.category === "custom" ? o.label || o.trigger || "" : o.trigger?.trim() || says[o.category] || kinds[o.category] || o.category;
  const [list, setList] = useState<PlaybookList | null>(null);
  const [company, setCompany] = useState("");
  const [doc, setDoc] = useState<EditorDoc | null>(null);
  const [shape, setShape] = useState<Structure | null>(null);
  const [phase, setPhase] = useState<string | null>("Organizando vuestro playbook…");
  const [area, setArea] = useState<Area | null>(null);
  const [openRow, setOpenRow] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<"goal" | "orientation" | null>(null);
  const [draft, setDraft] = useState("");
  const [ask, setAsk] = useState("");
  const [thinking, setThinking] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const chatEnd = useRef<HTMLDivElement>(null);
  const [fresh, setFresh] = useState(false);
  const [trying, setTrying] = useState<string | null>(null);
  const [custom, setCustom] = useState("");
  const [review, setReview] = useState<ReviewCall | "loading" | "error" | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [importText, setImportText] = useState("");
  const [importing, setImporting] = useState<string | null>(null);
  const importFile = useRef<HTMLInputElement>(null);

  useEffect(() => {
    void playbooksApi.list().then(setList);
    void playbooksApi.company().then((c) => setCompany(JSON.stringify(c.knowledge, null, 1)));
  }, []);

  const label = list?.details?.[motion]?.label ?? "";
  const goalKey = list?.details?.[motion]?.goal ?? "";

  /** Vocify reads the playbook and organises it; the goal and orientation are kept when only the rest changed. */
  const organise = async (next: EditorDoc, keep?: Pick<Structure, "goal" | "alternatives" | "orientation">) => {
    const call = () => post<Partial<Structure>>("structure", { title: label, goal: GOALS[goalKey] ?? "", content: numbered(next, answerName), company, conduct: "" });
    const whole = (o: Partial<Structure>) => Boolean(o.goal && o.alternatives && o.orientation && o.steps && o.info && o.themes);
    // The model sometimes leaves a part out: one more try, then what came, with nothing missing.
    let out = await call();
    if (!whole(out)) out = await call();
    const full: Structure = {
      goal: out.goal ?? "",
      alternatives: out.alternatives ?? [],
      orientation: out.orientation ?? "",
      steps: out.steps ?? [],
      info: out.info ?? [],
      themes: out.themes ?? [],
    };
    setShape(keep ? { ...full, ...keep } : full);
  };

  useEffect(() => {
    if (!list || !company) return;
    let live = true;
    void (async () => {
      const next = await playbooksApi.editor(motion);
      if (!live) return;
      setDoc(next);
      await organise(next);
      if (live) setPhase(null);
    })().catch(() => live && setPhase("No se pudo organizar. Recarga la página."));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [list, company, motion]);

  const saveDoc = async (next: EditorDoc) => {
    setDoc(next);
    const saved = await playbooksApi.saveDraft(motion, payloadOf(next));
    setDoc(saved);
    return saved;
  };
  /** Removes at once and offers to undo, the way the rest of the app does: no confirmation to click through. */
  const remove = (name: string, run: () => void) => {
    const before = { shape, doc };
    setOpenRow(null);
    run();
    toast(`Quitado ${name}`, {
      action: {
        label: "Deshacer",
        onClick: () => {
          setShape(before.shape);
          if (before.doc) void saveDoc(before.doc);
        },
      },
    });
  };

  useEffect(() => {
    chatEnd.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [messages, thinking]);

  /** The orientation changed: a soft highlight so the eye finds it. */
  const flash = () => {
    setFresh(true);
    window.setTimeout(() => setFresh(false), 2500);
  };

  /** A change to the playbook asked in the chat: Vocify drafts it now, the manager applies it or not. */
  const playbookProposal = async (instruction: string, answer: string): Promise<Proposal | undefined> => {
    if (!doc || !shape) return undefined;
    const result = await playbooksApi.fill(motion, { kind: "text", payload: instruction }, payloadOf(doc));
    if (!result.changes) return undefined;
    const built = editorFromStructure(result, newStepKey);
    const keep = { goal: shape.goal, alternatives: shape.alternatives, orientation: shape.orientation };
    // What is new or reworded, shown as the playbook shows it (a removal is in the summary).
    const was = new Set([
      ...(doc.steps ?? []).map((x) => `${x.label}|${x.criterion ?? ""}`),
      ...(doc.qualification ?? []).map((x) => `${x.label}|${x.good ?? ""}`),
      ...(doc.objections ?? []).map((x) => `${answerName(x)}|${x.guidance ?? ""}`),
    ]);
    const items = [
      ...built.steps.map((x) => ({ title: x.label, body: x.criterion ?? "" })),
      ...built.qualification.map((x) => ({ title: x.label, body: x.good ?? "" })),
      ...built.objections.map((x) => ({ title: answerName(x as EditorDoc["objections"][number]), body: x.guidance ?? "" })),
    ].filter((x) => x.title && !was.has(`${x.title}|${x.body}`));
    return {
      summary: result.summary || answer,
      items: items.slice(0, 3),
      apply: async () => {
        const saved = await playbooksApi.saveDraft(motion, draftPayload(built.steps, built.objections, built.qualification));
        setDoc(saved);
        await organise(saved, keep);
      },
    };
  };

  /** The manager talks to Vocify: an answer, or a change it proposes (applied only from the chat). */
  const send = async (text: string, moment?: { them: string; say: string }) => {
    if (!shape || thinking) return;
    const quote = moment ? `«${moment.them}» → «${moment.say}»` : undefined;
    const history = messages.map((m) => ({ who: m.who, text: m.text }));
    setMessages((all) => [...all, { who: "user", text, quote }]);
    setAsk("");
    setArea("ai");
    setThinking(true);
    try {
      const asked = moment
        ? `En una prueba, el prospect dijo «${moment.them}» y Vocify sugirió «${moment.say}». No lo haría: ${text}. Ajusta la orientación para que no vuelva a pasar.`
        : text;
      const out = await post<{ answer: string; change: "none" | "orientation" | "goal" | "playbook"; text: string }>("chat", {
        title: label,
        goal: shape.goal,
        alternatives: shape.alternatives.map((a) => a.label).join(" · "),
        orientation: shape.orientation,
        content: doc ? numbered(doc, answerName) : "",
        company,
        history,
        text: asked,
      });
      const after = out.text.trim();
      let proposal: Proposal | undefined;
      if (out.change === "orientation" && after && after !== shape.orientation.trim()) {
        // The current paragraph is in front of them on the left: only the new one here.
        proposal = {
          summary: "Nueva orientación",
          after,
          apply: () => {
            setShape((s) => (s ? { ...s, orientation: after } : s));
            flash();
          },
        };
      } else if (out.change === "goal" && after && after !== shape.goal.trim()) {
        proposal = { summary: "Nuevo objetivo", before: shape.goal, after, apply: () => setShape((s) => (s ? { ...s, goal: after } : s)) };
      } else if (out.change === "playbook" && after) {
        proposal = await playbookProposal(after, out.answer);
      }
      setMessages((all) => [...all, { who: "vocify", text: out.answer, proposal }]);
    } catch {
      setMessages((all) => [...all, { who: "vocify", text: "No he podido responder. Prueba otra vez." }]);
    } finally {
      setThinking(false);
    }
  };
  const settle = (i: number, state: "applied" | "discarded") =>
    setMessages((all) => all.map((m, j) => (j === i && m.proposal ? { ...m, proposal: { ...m.proposal, state } } : m)));

  /** «Probar»: Vocify plays a situation (or listens to a real call) with the orientation as it is now. */
  const tryIt = async (key: string, scenario?: string) => {
    setTrying(key);
    setReview("loading");
    try {
      let call: { id: string; kind: string; buyer: { name: string; role: string; company: string; situation: string }; turns: Turn[] } | undefined;
      if (key === "unai") {
        const data = await fetch("/prototypes/playbook-page/data.json.local").then((r) => r.json());
        call = { id: "unai-816ba4f7", kind: "real", buyer: { name: "Unai", role: "Head of Sales", company: "Dilkar", situation: "" }, turns: data.turns };
      }
      const out = await post<{ call: { buyer: { name: string }; turns: Turn[] }; shown: { visible_t: number; say: string }[] }>("sample-call", {
        ...(call ? { call } : { kind: key, scenario }),
        motion,
        title: label,
        rules: shape?.orientation ? [shape.orientation] : [],
      });
      setReview({ name: out.call.buyer.name.split(" ")[0], turns: out.call.turns, shown: [...out.shown].sort((a, b) => a.visible_t - b.visible_t) });
    } catch {
      setReview("error");
    }
  };

  /** One import for everything: Vocify splits it by conversation and each one takes only its part. */
  const importAll = async (from: FillSource) => {
    const types = Object.entries(list?.details ?? {}).map(([key, d]) => ({ key, label: d.label }));
    setImporting("Leyéndolo…");
    try {
      const text = from.kind === "text" ? from.payload : (await playbooksApi.readCompany(from)).text;
      setImporting("Repartiéndolo entre vuestras conversaciones…");
      const routed = await post<{ parts: Record<string, string>; company: string }>("route", { text, types });
      const done: string[] = [];
      for (const type of types) {
        const part = routed.parts[type.key]?.trim();
        if (!part) continue;
        setImporting(`Añadiéndolo a «${type.label}»…`);
        const current = await playbooksApi.editor(type.key);
        const result = await playbooksApi.fill(type.key, { kind: "text", payload: `Añade o corrige en este playbook lo que dice este texto:\n\n${part}` }, payloadOf(current));
        if (!result.changes) continue;
        const built = editorFromStructure(result, newStepKey);
        const saved = await playbooksApi.saveDraft(type.key, draftPayload(built.steps, built.objections, built.qualification));
        done.push(`${type.label} (${result.changes})`);
        if (type.key === motion && shape) {
          setDoc(saved);
          await organise(saved, { goal: shape.goal, alternatives: shape.alternatives, orientation: shape.orientation });
        }
      }
      const forCompany = routed.company.trim() ? " · lo general de la empresa no se guarda en el prototipo" : "";
      toast(done.length ? `Importado en ${done.join(" · ")}${forCompany}` : `No había nada nuevo para vuestras conversaciones${forCompany}`);
      setImportOpen(false);
      setImportText("");
    } catch {
      toast.error("No se pudo importar. Prueba otra vez.");
    } finally {
      setImporting(null);
    }
  };
  const importPicked = async (picked: File | undefined) => {
    if (!picked) return;
    const kind = sourceKindForFile(picked);
    if (!kind) return;
    await importAll({ kind, payload: kind === "text" ? await picked.text() : await blobBase64(picked), name: picked.name });
  };

  const steps = doc?.steps ?? [];
  const info = doc?.qualification ?? [];
  const answers = doc?.objections ?? NO_ANSWERS;
  const themes = useMemo(() => {
    const placed = new Set((shape?.themes ?? []).flatMap((theme) => theme.answers));
    const rest = answers.map((_, i) => i + 1).filter((n) => !placed.has(n));
    return [...(shape?.themes ?? []), ...(rest.length ? [{ name: "Otras", answers: rest }] : [])];
  }, [shape, answers]);
  const titles: Record<Area, string> = { steps: "Guía de conversación", info: "Cualificación", answers: "Objeciones y respuestas", test: "Probar", ai: "Vocify" };
  // The same icons the playbook's tabs use (Pasos, Cualificación, Objeciones).
  const icons: Record<Area, LucideIcon> = { steps: ListOrdered, info: Target, answers: MessagesSquare, test: Play, ai: Sparkles };
  const knows: { key: Area; count: number }[] = [
    { key: "steps", count: steps.length },
    { key: "info", count: info.length },
    { key: "answers", count: answers.length },
  ];
  const setInfoMeta = (n: number, patch: Partial<Structure["info"][number]>) =>
    setShape((s) => (s ? { ...s, info: s.info.map((m) => (m.n === n ? { ...m, ...patch } : m)) } : s));
  const setStepMeta = (n: number, patch: Partial<Structure["steps"][number]>) =>
    setShape((s) => (s ? { ...s, steps: s.steps.map((m) => (m.n === n ? { ...m, ...patch } : m)) } : s));

  /** «+» in the open panel: a new item, open and ready to type in, at the end of its list. */
  const add = () => {
    if (!doc) return;
    if (area === "steps") {
      void saveDoc({ ...doc, steps: [...steps, { label: "", criterion: "" }] as EditorDoc["steps"] });
      setOpenRow(steps.length);
    } else if (area === "info") {
      void saveDoc({ ...doc, qualification: [...info, { label: "", good: "" }] as EditorDoc["qualification"] });
      setOpenRow(info.length);
    } else if (area === "answers") {
      const taken = answers.filter((o) => o.category === "custom").map((o) => o.id ?? "");
      void saveDoc({ ...doc, objections: [...answers, { category: "custom", id: customObjectionId("nueva", taken), label: "", trigger: "", guidance: "" }] as EditorDoc["objections"] });
      setOpenRow(answers.length);
    }
  };

  /** The information opened on the side: the playbook's own rows (DocRow), edited where they are read. */
  const panel = (() => {
    if (!shape || !doc || !area || area === "test" || area === "ai") return null;
    const row = (i: number, mark: ReactNode, title: { value: string; placeholder: string; save: (v: string) => void }, body: string, right: string | null, detail: ReactNode, onRemove: () => void) => {
      const open = openRow === i;
      const toggle = () => setOpenRow(open ? null : i);
      return (
        <DocRow
          key={`${area}-${i}`}
          lead={
            open ? (
              <span className="-my-2">
                <IconAction label="Cerrar" expanded onClick={toggle}>
                  <ChevronDown size={16} strokeWidth={1.5} className="rotate-180" />
                </IconAction>
              </span>
            ) : (
              mark
            )
          }
          title={
            open ? (
              <InlineTextarea
                autoFocus={!title.value}
                className={itemTitle}
                defaultValue={title.value}
                placeholder={title.placeholder}
                onKeyDown={(e) => e.key === "Enter" && e.preventDefault()}
                onBlur={(e) => e.target.value.trim() !== title.value && title.save(e.target.value.replace(/\n/g, " ").trim())}
              />
            ) : (
              <button type="button" onClick={toggle} className="block w-full rounded-md text-left">
                <span className={cn(itemTitle, "block", !title.value && "text-muted-foreground")}>{title.value || title.placeholder}</span>
                {body ? <span className={cn(itemBody, "mt-0.5 block line-clamp-2")}>{body}</span> : null}
              </button>
            )
          }
          side={
            <>
              {right ? <span className="whitespace-nowrap text-xs text-muted-foreground">{right}</span> : null}
              <ItemMenu label={`Opciones de ${title.value || "este elemento"}`} actions={[{ label: "Quitar", danger: true, onSelect: onRemove }]} />
            </>
          }
        >
          {open ? <div className="space-y-3 pb-1">{detail}</div> : null}
        </DocRow>
      );
    };
    const labelled = (name: string, child: ReactNode) => (
      <div>
        <p className={THEME_TOKENS.typography.fieldLabel}>{name}</p>
        {child}
      </div>
    );
    if (area === "steps") {
      return (
        <ol>
          {steps.map((step, i) => {
            const meta = shape.steps.find((m) => m.n === i + 1);
            return row(
              i,
              <NumberMark n={i + 1} />,
              { value: step.label, placeholder: "Nombre del paso", save: (v) => void saveDoc({ ...doc, steps: steps.map((s, j) => (j === i ? { ...s, label: v } : s)) }) },
              meta?.when ?? "",
              null,
              <>
                {labelled("Cuándo tiene sentido", <InlineTextarea className={itemBody} defaultValue={meta?.when ?? ""} placeholder="La situación en la que ayuda" onBlur={(e) => setStepMeta(i + 1, { when: e.target.value })} />)}
                {labelled(
                  "Qué buscamos conseguir",
                  <InlineTextarea className={itemBody} defaultValue={step.criterion ?? ""} placeholder="Para qué existe este momento" onBlur={(e) => void saveDoc({ ...doc, steps: steps.map((s, j) => (j === i ? { ...s, criterion: e.target.value } : s)) })} />,
                )}
                {labelled(
                  "Ejemplo de referencia",
                  <InlineTextarea
                    className={cn(itemBody, "italic text-muted-foreground")}
                    defaultValue={step.example ?? ""}
                    placeholder="Opcional"
                    onBlur={(e) => void saveDoc({ ...doc, steps: steps.map((s, j) => (j === i ? { ...s, example: e.target.value } : s)) })}
                  />,
                )}
              </>,
              () =>
                remove(`«${step.label || "paso"}»`, () => {
                  setShape((st) => (st ? { ...st, steps: st.steps.filter((m) => m.n !== i + 1).map((m) => (m.n > i + 1 ? { ...m, n: m.n - 1 } : m)) } : st));
                  void saveDoc({ ...doc, steps: steps.filter((_, j) => j !== i) });
                }),
            );
          })}
        </ol>
      );
    }
    if (area === "info") {
      return (
        <ul>
          {info.map((item, i) => {
            const meta = shape.info.find((m) => m.n === i + 1);
            return row(
              i,
              <span className={cn("mt-1.5 h-1.5 w-1.5 rounded-full", meta?.essential ? "bg-foreground" : "border border-muted-foreground/60")} />,
              { value: item.label, placeholder: "Qué hay que averiguar", save: (v) => void saveDoc({ ...doc, qualification: info.map((q, j) => (j === i ? { ...q, label: v } : q)) }) },
              item.good?.trim() || meta?.evidence || "",
              meta?.essential ? "Esencial" : "Opcional",
              <>
                {labelled(
                  "Cuenta como respuesta",
                  <InlineTextarea
                    className={itemBody}
                    defaultValue={item.good?.trim() || meta?.evidence || ""}
                    placeholder="Cómo suena una respuesta real"
                    onBlur={(e) => void saveDoc({ ...doc, qualification: info.map((q, j) => (j === i ? { ...q, good: e.target.value } : q)) })}
                  />,
                )}
                {labelled("No cuenta", <InlineTextarea className={cn(itemBody, "text-muted-foreground")} defaultValue={meta?.not_evidence ?? ""} placeholder="Lo que parece una respuesta y no lo es" onBlur={(e) => setInfoMeta(i + 1, { not_evidence: e.target.value })} />)}
                {labelled(
                  "Para el objetivo es",
                  <Segmented
                    aria-label="Para el objetivo es"
                    value={meta?.essential ? "essential" : "optional"}
                    onValueChange={(value) => setInfoMeta(i + 1, { essential: value === "essential" })}
                    options={[
                      { value: "essential", label: "Esencial" },
                      { value: "optional", label: "Opcional" },
                    ]}
                  />,
                )}
              </>,
              () =>
                remove(`«${item.label || "dato"}»`, () => {
                  setShape((st) => (st ? { ...st, info: st.info.filter((m) => m.n !== i + 1).map((m) => (m.n > i + 1 ? { ...m, n: m.n - 1 } : m)) } : st));
                  void saveDoc({ ...doc, qualification: info.filter((_, j) => j !== i) });
                }),
            );
          })}
        </ul>
      );
    }
    const q = query.trim().toLowerCase();
    return (
      <div className="space-y-4">
        <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Buscar lo que dicen" className="h-8" />
        {themes.map((theme) => {
          const items = theme.answers.filter((n) => answers[n - 1] && (!q || `${answerName(answers[n - 1])} ${answers[n - 1].guidance}`.toLowerCase().includes(q)));
          if (!items.length) return null;
          return (
            <section key={theme.name}>
              <h3 className="text-[12.5px] font-medium text-muted-foreground">
                {theme.name} · {items.length}
              </h3>
              <ul>
                {items.map((n) => {
                  const o = answers[n - 1];
                  return row(
                    n - 1,
                    <QuoteMark />,
                    {
                      value: answerName(o),
                      placeholder: "Lo que dice el cliente",
                      save: (v) => void saveDoc({ ...doc, objections: answers.map((x, j) => (j === n - 1 ? (x.category === "custom" ? { ...x, label: v } : { ...x, trigger: v }) : x)) }),
                    },
                    o.guidance ?? "",
                    null,
                    labelled(
                      "Qué responder",
                      <InlineTextarea
                        className={itemBody}
                        defaultValue={o.guidance ?? ""}
                        placeholder="La respuesta que verá el comercial"
                        onBlur={(e) => void saveDoc({ ...doc, objections: answers.map((x, j) => (j === n - 1 ? { ...x, guidance: e.target.value } : x)) })}
                      />,
                    ),
                    () =>
                      remove(`«${answerName(o) || "respuesta"}»`, () => {
                        setShape((st) =>
                          st ? { ...st, themes: st.themes.map((th) => ({ ...th, answers: th.answers.filter((x) => x !== n).map((x) => (x > n ? x - 1 : x)) })) } : st,
                        );
                        void saveDoc({ ...doc, objections: answers.filter((_, j) => j !== n - 1) });
                      }),
                  );
                })}
              </ul>
            </section>
          );
        })}
      </div>
    );
  })();

  /** «Probar», on the side: a situation (or a real call) and what Vocify suggests in it. */
  const testPanel = (() => {
    if (area !== "test" || !shape) return null;
    const options = [
      ...TRIES,
      { key: "custom", label: "Tu situación", icon: PencilLine },
      ...(motion === "discovery" ? [{ key: "unai", label: "Una llamada real", icon: PhoneCall }] : []),
    ];
    return (
      <div className="space-y-4">
        <div className="flex flex-wrap gap-1.5">
          {options.map((item) => {
            const Icon = item.icon;
            const on = trying === item.key;
            return (
              <button
                key={item.key}
                type="button"
                disabled={review === "loading"}
                onClick={() => (item.key === "custom" ? (setTrying("custom"), setReview(null)) : void tryIt(item.key))}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[13px] transition-colors",
                  on ? "border-foreground bg-foreground text-background" : "border-border text-foreground/80 hover:border-foreground/40",
                )}
              >
                {on && review === "loading" ? <VocifySpinner size={11} /> : <Icon size={13} strokeWidth={1.5} />}
                {item.label}
              </button>
            );
          })}
        </div>
        {trying === "custom" && review !== "loading" ? (
          <form
            className="flex items-center gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (custom.trim()) void tryIt("custom", custom.trim());
            }}
          >
            <Input autoFocus value={custom} onChange={(e) => setCustom(e.target.value)} placeholder="Ej.: acaba de contratar 3 comerciales nuevos" className="h-8 flex-1 text-[13px]" />
            <Button type="submit" size="sm" disabled={!custom.trim()}>
              Probar
            </Button>
          </form>
        ) : null}
        {review === "loading" ? (
          <p className="text-[13px] text-muted-foreground">{trying === "unai" ? "Escuchando la llamada con Unai, hasta 3 minutos…" : "Vocify juega la situación, unos 30 s…"}</p>
        ) : review === "error" ? (
          <p className="text-[13px] text-destructive">No se pudo. Prueba otra vez.</p>
        ) : review ? (
          review.shown.length ? (
            <ul>
              {review.shown.map((card) => {
                const turns = review.turns.filter((turn) => turn.t <= card.visible_t);
                const them = [...turns].reverse().find((turn) => turn.who === "them" && turn.text.split(" ").length >= 3)?.text ?? "";
                return (
                  <Moment
                    key={`${card.visible_t}-${card.say}`}
                    them={them}
                    say={card.say}
                    at={card.visible_t}
                    label={review.name}
                    onCorrect={(feedback) => send(feedback, { them, say: card.say })}
                  />
                );
              })}
            </ul>
          ) : (
            <p className="text-[13px] text-muted-foreground">Aquí Vocify no sugeriría nada.</p>
          )
        ) : (
          <p className="text-[13px] text-muted-foreground">Elige una situación: Vocify la juega con lo que sabe y te enseña qué sugeriría. Si algo no te gusta, díselo y Vocify propone cómo ajustarlo.</p>
        )}
      </div>
    );
  })();

  /** The chat with Vocify: the conversation scrolls, the box to write stays at the bottom. */
  const chatPanel = (
    <>
      <p className="pt-1 text-[13px] text-muted-foreground">Pregúntale por este playbook o pídele un cambio. Nada se aplica sin que lo apruebes.</p>
      <div className="app-scroll mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto pb-4 pr-2">
        {messages.length === 0 ? (
          <div className="flex flex-col items-start gap-1.5">
            {CHAT_HINTS.map((hint) => (
              <button key={hint} type="button" onClick={() => void send(hint)} className="rounded-full border border-border px-3 py-1 text-[13px] text-foreground/80 hover:border-foreground/40">
                {hint}
              </button>
            ))}
          </div>
        ) : (
          messages.map((m, i) =>
            m.who === "user" ? (
              <div key={i} className="ml-8 space-y-1">
                {m.quote ? <p className="text-right text-[12px] leading-snug text-muted-foreground">{m.quote}</p> : null}
                <p className="ml-auto w-fit rounded-2xl rounded-br-md bg-secondary px-3 py-2 text-[14px] leading-snug text-foreground">{m.text}</p>
              </div>
            ) : (
              <div key={i} className="space-y-2">
                <p className="text-[14px] leading-relaxed text-foreground">{m.text}</p>
                {m.proposal ? <ProposalBox proposal={m.proposal} onSettle={(state) => settle(i, state)} /> : null}
              </div>
            ),
          )
        )}
        {thinking ? (
          <p className="inline-flex items-center gap-2 text-[13px] text-muted-foreground" role="status">
            <VocifySpinner size={12} />
            Pensando…
          </p>
        ) : null}
        <div ref={chatEnd} />
      </div>
      <form
        className="flex items-end gap-2 border-t border-border pb-1 pt-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (ask.trim()) void send(ask.trim());
        }}
      >
        <textarea
          autoFocus
          rows={2}
          value={ask}
          disabled={thinking}
          onChange={(e) => setAsk(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (ask.trim()) void send(ask.trim());
            }
          }}
          placeholder="Escribe a Vocify…"
          className={cn(field, "flex-1")}
        />
        <IconAction label="Enviar" tone="primary" disabled={!ask.trim() || thinking} onClick={() => void send(ask.trim())}>
          <ArrowUp size={16} strokeWidth={1.5} />
        </IconAction>
      </form>
    </>
  );

  const pencil = (on: () => void) => (
    <button type="button" onClick={on} className="inline-flex items-center gap-1.5 text-[13px] text-muted-foreground hover:text-foreground">
      <Pencil size={12} strokeWidth={1.5} />
      Editar
    </button>
  );

  return (
    // The funnel's window is 88vh with 2rem of padding: the workspace fills it and each column scrolls on its own.
    <div className="flex h-[calc(88vh-4rem)] min-h-0 gap-8">
      <main className="app-scroll flex min-w-0 flex-1 flex-col gap-7 overflow-y-auto pr-2">
        <header className="flex items-end gap-3">
          <div className="min-w-0 flex-1">
            <p className={THEME_TOKENS.typography.capsLabel}>Playbook</p>
            <h1 className={cn(THEME_TOKENS.typography.pageTitle, "mt-1")}>{label}</h1>
          </div>
          <Button type="button" variant="ghost" size="sm" onClick={() => setImportOpen(true)}>
            <FileUp size={14} strokeWidth={1.5} />
            Importar
          </Button>
          <Button type="button" variant="outline" size="sm" aria-pressed={area === "test"} className={cn(area === "test" && "bg-secondary")} onClick={() => setArea(area === "test" ? null : "test")}>
            <Play size={14} strokeWidth={1.5} />
            Probar
          </Button>
          <Button type="button" variant="outline" size="sm" aria-pressed={area === "ai"} className={cn(area === "ai" && "bg-secondary")} onClick={() => setArea(area === "ai" ? null : "ai")}>
            <Sparkles size={14} strokeWidth={1.5} className="text-beige" />
            Preguntar a Vocify
          </Button>
        </header>

        {phase || !shape ? (
          <p className="inline-flex items-center gap-2 text-[15px] text-muted-foreground" role="status">
            <VocifySpinner size={12} />
            {phase ?? "Organizando vuestro playbook…"}
          </p>
        ) : (
          <>
            <Block n={1} title="¿Qué queremos conseguir?" action={editing !== "goal" ? pencil(() => { setDraft(shape.goal); setEditing("goal"); }) : null}>
              {editing === "goal" ? (
                <div className="flex gap-2">
                  <Input autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} className="h-10 flex-1 text-[16px]" />
                  <Button type="button" size="sm" className="h-10" disabled={!draft.trim()} onClick={() => { setShape({ ...shape, goal: draft.trim() }); setEditing(null); }}>
                    Guardar
                  </Button>
                </div>
              ) : (
                <p className="text-[17px] leading-snug text-foreground">{shape.goal}</p>
              )}
              {shape.alternatives.length ? <p className="pt-1 text-[13.5px] text-muted-foreground">También vale: {shape.alternatives.map((a) => a.label).join(" · ")}</p> : null}
            </Block>

            <Block
              n={2}
              title="¿Cómo queremos que ayude Vocify?"
              lead="La orientación para sus tarjetas en este tipo de conversación."
              action={editing !== "orientation" ? pencil(() => { setDraft(shape.orientation); setEditing("orientation"); }) : null}
            >
              {editing === "orientation" ? (
                <div className="space-y-2">
                  <textarea autoFocus className={cn(field, "min-h-[7rem] text-[15px]")} value={draft} onChange={(e) => setDraft(e.target.value)} />
                  <div className="flex gap-2">
                    <Button type="button" size="sm" disabled={!draft.trim()} onClick={() => { setShape({ ...shape, orientation: draft.trim() }); setEditing(null); }}>
                      Guardar
                    </Button>
                    <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(null)}>
                      Cancelar
                    </Button>
                  </div>
                </div>
              ) : (
                <p className={cn("rounded-xl px-4 py-3 text-[15.5px] leading-relaxed text-foreground transition-colors duration-700", fresh ? "bg-beige/10" : "bg-card")}>{shape.orientation}</p>
              )}
              {editing !== "orientation" ? (
                <button type="button" onClick={() => setArea("ai")} className="mt-2 inline-flex items-center gap-1.5 text-[13px] text-muted-foreground hover:text-foreground">
                  <Sparkles size={13} strokeWidth={1.5} className="text-beige" />
                  Pedir un cambio a Vocify
                </button>
              ) : null}
            </Block>

            <Block n={3} title="¿Con qué información trabaja?">
              <ul className="divide-y divide-border/60 border-y border-border/60">
                {knows.map((item) => {
                  const Icon = icons[item.key];
                  return (
                    <li key={item.key}>
                      <button
                        type="button"
                        onClick={() => {
                          setArea(area === item.key ? null : item.key);
                          setOpenRow(null);
                        }}
                        aria-expanded={area === item.key}
                        className={cn("flex w-full items-center gap-3 px-2 py-3 text-left", THEME_TOKENS.interaction.rowHover, area === item.key && "bg-secondary/60")}
                      >
                        <Icon size={16} strokeWidth={1.5} className="text-muted-foreground" />
                        <span className="flex-1 text-[15px] text-foreground">{titles[item.key]}</span>
                        <span className="text-[13px] tabular-nums text-muted-foreground">{item.count}</span>
                        <ChevronRight size={15} strokeWidth={1.5} className="text-muted-foreground" />
                      </button>
                    </li>
                  );
                })}
              </ul>
              <p className="pt-2 text-[13px] text-muted-foreground">
                Y lo que sabe de vuestra empresa y los documentos importados.{" "}
                <button type="button" onClick={() => setImportOpen(true)} className="text-foreground underline-offset-2 hover:underline">
                  Importar más
                </button>
              </p>
            </Block>
          </>
        )}
      </main>

      {/* The information or «Probar», on the side only while it is open. */}
      {area ? (
        <aside className="flex w-[24rem] shrink-0 flex-col border-l border-border pl-6">
          <div className="flex items-center gap-2 pr-8 pt-1">
            {(() => {
              const Icon = icons[area];
              return <Icon size={18} strokeWidth={1.5} className="text-muted-foreground" />;
            })()}
            <h2 className={cn(THEME_TOKENS.typography.panelTitle, "flex-1")}>{titles[area]}</h2>
            {area !== "test" && area !== "ai" ? (
              <IconAction label="Añadir" onClick={add}>
                <Plus size={16} strokeWidth={1.5} />
              </IconAction>
            ) : null}
            <IconAction label="Cerrar" onClick={() => setArea(null)}>
              <X size={16} strokeWidth={1.5} />
            </IconAction>
          </div>
          {area === "steps" ? <p className="pt-1 text-[13px] text-muted-foreground">Orientativa: Vocify no obliga a seguir el orden ni a pasar por todos.</p> : null}
          {area === "ai" ? chatPanel : <div className="app-scroll mt-4 min-h-0 flex-1 overflow-y-auto pb-6 pr-2">{area === "test" ? testPanel : panel}</div>}
        </aside>
      ) : null}

      <WindowShell
        open={importOpen}
        onOpenChange={(open) => !importing && setImportOpen(open)}
        title="Importar"
        lead="Pega lo que tengáis, tal cual: un Google Doc, un Notion, unas notas, aunque mezcle llamadas. Vocify lo reparte."
        footer={
          <>
            <button type="button" className="text-[13px] text-muted-foreground hover:text-foreground" disabled={Boolean(importing)} onClick={() => importFile.current?.click()}>
              o elige un archivo (PDF, audio, texto)
            </button>
            <Button type="button" size="sm" disabled={!importText.trim() || Boolean(importing)} onClick={() => void importAll({ kind: "text", payload: importText.trim() })}>
              {importing ? <VocifySpinner size={12} /> : null}
              {importing ?? "Importar"}
            </Button>
          </>
        }
      >
        <textarea className={cn(field, "min-h-[16rem]")} value={importText} disabled={Boolean(importing)} onChange={(event) => setImportText(event.target.value)} placeholder="Pega aquí vuestro playbook" />
        <input
          ref={importFile}
          type="file"
          className="sr-only"
          tabIndex={-1}
          accept="application/pdf,.pdf,audio/*,.m4a,.mp3,.wav,.txt,.md,text/plain"
          onChange={(event) => {
            const picked = event.target.files?.[0];
            event.target.value = "";
            void importPicked(picked);
          }}
        />
      </WindowShell>
    </div>
  );
}
