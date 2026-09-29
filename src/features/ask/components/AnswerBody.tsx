import { Quotes } from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import { parseBlocks, type Inline } from "@/lib/ask-markdown";
import { displayText, type AskEvidence } from "@/lib/ask-thread";
import { useSmoothText } from "../hooks/useSmoothText";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useLanguage } from "@/lib/i18n";

function EvidenceChip({ n, evidence }: { n: number; evidence?: AskEvidence }) {
  const { t } = useLanguage();
  if (!evidence) return <span className="text-muted-foreground">[{n}]</span>;
  const who = evidence.speaker === "prospect" ? t.product.askSpeakerProspect : evidence.speaker === "rep" ? t.product.askSpeakerRep : null;
  const when = evidence.at ? new Date(evidence.at).toLocaleDateString(undefined, { day: "numeric", month: "short" }) : null;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="mx-0.5 inline-flex h-5 min-w-5 items-center justify-center gap-0.5 rounded-full border border-border/70 bg-secondary/60 px-1.5 align-baseline text-[12px] leading-none text-foreground transition-colors hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label={`${t.product.askEvidenceFrom} ${n}`}
        >
          <Quotes size={10} weight="light" aria-hidden="true" />
          {n}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-72 space-y-2 rounded-xl border-border/70 p-3 shadow-sm">
        <p className="text-[13px] leading-relaxed text-foreground">“{evidence.quote}”</p>
        <p className="text-[12px] text-muted-foreground">
          {[who, evidence.rep, when].filter(Boolean).join(" · ")}
        </p>
        {evidence.memo_id ? (
          <Link to={`/dashboard/memos/${evidence.memo_id}`} className="inline-block text-[13px] text-primary underline-offset-4 hover:underline">
            {t.product.askEvidenceOpen}
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
    <div className="space-y-3 text-[15px] leading-[1.65] text-foreground">
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
          <div key={i} className="overflow-x-auto rounded-xl border border-border/70">
            <table className="w-full border-collapse text-[13px] tabular-nums">
              <thead>
                <tr className="text-left text-muted-foreground">
                  {block.head.map((cell, j) => (
                    <th key={j} className="px-3 py-2 font-normal"><Inlines nodes={cell} evidence={evidence} /></th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {block.rows.slice(0, 8).map((row, r) => (
                  <tr key={r} className="border-t border-border/60">
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
