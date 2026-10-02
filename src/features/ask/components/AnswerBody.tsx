import { BookOpenText, Quote } from "lucide-react";
import { Link } from "react-router-dom";
import { useAuth } from "@/features/auth";
import { isManagerRole } from "@/lib/nav";
import { objectionDisplayName, teamFlowFilterLabel } from "@/lib/team-insights";
import { parseBlocks, type Inline } from "@/lib/ask-markdown";
import { displayText, type AskEvidence } from "@/lib/ask-thread";
import { useSmoothText } from "../hooks/useSmoothText";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useLanguage } from "@/lib/i18n";

function EvidenceChip({ n, evidence }: { n: number; evidence?: AskEvidence }) {
  const { t } = useLanguage();
  const { user } = useAuth();
  const p = t.product;
  if (!evidence) return <span className="text-muted-foreground">[{n}]</span>;
  const playbook = evidence.speaker === "playbook";
  const who = playbook
    ? p.askPlaybookSource
    : evidence.speaker === "prospect"
      ? p.askSpeakerProspect
      : evidence.speaker === "rep"
        ? p.askSpeakerRep
        : null;
  const context = playbook
    ? [evidence.category ? objectionDisplayName(evidence.category, p.objections) : null, evidence.rep ? teamFlowFilterLabel(evidence.rep, p, p.motions) : null]
    : [evidence.rep, evidence.at ? new Date(evidence.at).toLocaleDateString(p.hourLocale, { day: "numeric", month: "short" }) : null];
  const Icon = playbook ? BookOpenText : Quote;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={`mx-0.5 inline-flex h-[18px] min-w-[18px] -translate-y-px items-center justify-center gap-0.5 rounded-full border px-1.5 align-middle text-[11px] leading-none transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
            playbook ? "border-beige/30 bg-beige/10 text-beige hover:bg-beige/15" : "border-[hsl(var(--hairline))] bg-secondary/60 text-foreground hover:bg-secondary"
          }`}
          aria-label={`${playbook ? p.askPlaybookSource : p.askEvidenceFrom} ${n}`}
        >
          <Icon size={10} strokeWidth={playbook ? 2.25 : 1.5} aria-hidden="true" />
          {n}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-72 space-y-2 p-3.5">
        <p className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
          <Icon size={12} strokeWidth={1.5} aria-hidden="true" />
          {[who, ...context].filter(Boolean).join(" · ")}
        </p>
        <p className="text-[13.5px] leading-relaxed text-foreground">“{evidence.quote}”</p>
        {playbook ? (
          <Link
            to={isManagerRole(user?.company?.role) ? "/dashboard/process" : "/dashboard/coach?tab=playbook"}
            className="inline-block text-[13px] text-primary underline-offset-4 hover:underline"
          >
            {p.navPlaybook}
          </Link>
        ) : evidence.memo_id ? (
          <Link to={`/dashboard/memos/${evidence.memo_id}`} className="inline-block text-[13px] text-primary underline-offset-4 hover:underline">
            {p.askEvidenceOpen}
          </Link>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}

function Inlines({ nodes, evidence }: { nodes: Inline[]; evidence: AskEvidence[] }) {
  return (
    <>
      {nodes.map((node, i) => {
        switch (node.t) {
          case "bold":
            return <strong key={i} className="font-medium text-foreground">{node.v}</strong>;
          case "code":
            return <code key={i} className="rounded bg-secondary/70 px-1 py-0.5 text-[13px]">{node.v}</code>;
          case "cite":
            return <EvidenceChip key={i} n={node.n} evidence={evidence[node.n - 1]} />;
          case "link":
            return (
              <a key={i} href={node.href} target="_blank" rel="noreferrer" className="text-primary underline underline-offset-4 hover:opacity-80">
                {node.label}
              </a>
            );
          default:
            return <span key={i}>{node.v}</span>;
        }
      })}
    </>
  );
}

/** Answer text as blocks. Nothing here becomes HTML; citations open the quote they point to. */
export default function AnswerBody({ text, evidence, streaming }: { text: string; evidence: AskEvidence[]; streaming: boolean }) {
  const visible = useSmoothText(text, streaming);
  const arriving = streaming || visible.length < text.length;
  const blocks = parseBlocks(arriving ? displayText(visible) : text);
  return (
    <div className="space-y-3 text-[15px] leading-[1.65] text-foreground [overflow-wrap:anywhere]">
      {blocks.map((block, i) => {
        if (block.t === "p") {
          return <p key={i} className="whitespace-pre-line"><Inlines nodes={block.inline} evidence={evidence} /></p>;
        }
        if (block.t === "ul" || block.t === "ol") {
          const List = block.t;
          return (
            <List key={i} className={`space-y-1.5 pl-5 ${List === "ul" ? "list-disc" : "list-decimal"} marker:text-muted-foreground`}>
              {block.items.map((item, j) => (
                <li key={j}><Inlines nodes={item} evidence={evidence} /></li>
              ))}
            </List>
          );
        }
        return (
          <div key={i} className="overflow-x-auto rounded-xl border border-[hsl(var(--hairline))] bg-card/70">
            <table className="w-full border-collapse text-[13px] tabular-nums">
              <thead>
                <tr className="bg-secondary/30 text-left text-muted-foreground">
                  {block.head.map((cell, j) => (
                    <th key={j} className="px-3 py-2 font-normal"><Inlines nodes={cell} evidence={evidence} /></th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {block.rows.slice(0, 8).map((row, r) => (
                  <tr key={r} className="border-t border-[hsl(var(--hairline))]">
                    {row.map((cell, c) => (
                      <td key={c} className="px-3 py-2 text-foreground"><Inlines nodes={cell} evidence={evidence} /></td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      })}
    </div>
  );
}
