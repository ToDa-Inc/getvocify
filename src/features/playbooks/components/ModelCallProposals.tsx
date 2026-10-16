import { useState } from "react";
import { Pencil, Repeat2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { QuoteBubble } from "@/features/playbooks/components/Bubbles";
import type { ModelProposal, ProposalSpeaker } from "@/features/playbooks/assistantApi";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

const card = `${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card}`;

export type ProposalsViewProps = {
  proposals: ModelProposal[];
  /** The name of step number `index` (1-based). */
  stepLabel: (index: number) => string;
  /** The name an objection goes by (a fixed category or the team's own). */
  objectionLabel: (proposal: ModelProposal) => string;
  speakerWarning: boolean;
  swapped: boolean;
  chosen: Record<string, boolean>;
  texts: Record<string, string>;
  /** Why a proposal could not be applied, by id (the server's code). */
  skipped: Record<string, string>;
  applying: boolean;
  onToggle: (id: string, on: boolean) => void;
  onText: (id: string, text: string) => void;
  onDiscard: (id: string) => void;
  onSwap: () => void;
  onApply: () => void;
  onOwn: (id: string, name: string) => void;
};

const SWAP: Record<ProposalSpeaker, ProposalSpeaker> = { rep: "client", client: "rep", unknown: "unknown" };

/** One proposal: where it comes from (the passage, with who speaks), what Vocify would keep, and what to do with it. */
function ProposalCard({ proposal, props }: { proposal: ModelProposal; props: ProposalsViewProps }) {
  const { t } = useLanguage();
  const c = t.product.pb2.improve;
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const text = props.texts[proposal.id] ?? proposal.text;
  const on = props.chosen[proposal.id] !== false;
  const code = props.skipped[proposal.id];
  const speaker = (side: ProposalSpeaker) => {
    const shown = props.swapped ? SWAP[side] : side;
    return shown === "rep" ? c.speakerRep : shown === "client" ? c.speakerClient : c.speakerUnknown;
  };
  const title =
    proposal.kind === "step_example"
      ? c.proposalStep.replace("{step}", props.stepLabel(proposal.step_index ?? 0))
      : c.proposalBranch.replace("{objection}", props.objectionLabel(proposal)).replace("{when}", proposal.when ?? "");
  return (
    <li className={cn(card, "space-y-3 p-4", !on && "opacity-60")}>
      <div className="flex items-start justify-between gap-3">
        <p className={THEME_TOKENS.typography.groupTitle}>{title}</p>
        <Switch checked={on} onCheckedChange={(next) => props.onToggle(proposal.id, next)} aria-label={c.proposalUse} />
      </div>
      <div className="space-y-2">
        {proposal.excerpt.map((part, index) => (
          <QuoteBubble key={index} label={speaker(part.speaker)}>
            {part.text}
          </QuoteBubble>
        ))}
      </div>
      {editing ? (
        <textarea
          value={text}
          rows={3}
          autoFocus
          aria-label={c.proposalEdit}
          className={cn(THEME_TOKENS.radius.control, "block w-full resize-y border border-border bg-background px-3 py-2 text-[14.5px] leading-relaxed text-foreground focus:outline-none focus:ring-1 focus:ring-beige/40")}
          onChange={(event) => props.onText(proposal.id, event.target.value)}
          onBlur={() => setEditing(false)}
        />
      ) : (
        <p className={cn(THEME_TOKENS.typography.itemBody, "break-words")}>{text}</p>
      )}
      <div className="flex flex-wrap items-center gap-1">
        <Button type="button" variant="quiet" size="text" onClick={() => setEditing((now) => !now)}>
          <Pencil aria-hidden strokeWidth={1.5} />
          {c.proposalEdit}
        </Button>
        <Button type="button" variant="quiet" size="text" onClick={() => props.onDiscard(proposal.id)}>
          {c.proposalDiscard}
        </Button>
      </div>
      {code ? (
        <div className="space-y-2" role="alert">
          <p className="text-[13px] text-destructive">{code === "guidance_too_long" ? c.skippedLong : c.skippedGeneric}</p>
          {code === "guidance_too_long" ? (
            <div className="flex flex-wrap items-center gap-2">
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder={c.ownName}
                aria-label={c.ownName}
                maxLength={60}
                className={cn(THEME_TOKENS.radius.control, "h-9 min-w-0 flex-1 border border-border bg-background px-3 text-sm focus:outline-none focus:ring-1 focus:ring-beige/40")}
              />
              <Button type="button" variant="outline" size="sm" disabled={!name.trim() || props.applying} onClick={() => props.onOwn(proposal.id, name.trim())}>
                {c.skippedOwn}
              </Button>
            </div>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

/**
 * "Esto es lo que he aprendido": what Vocify took from a model call, each with the passage it comes from. The Head of
 * Sales keeps what they want (a switch each), can rewrite it, and saves the chosen ones into the draft. Pure view.
 */
export function ModelCallProposalsView(props: ProposalsViewProps) {
  const { t } = useLanguage();
  const c = t.product.pb2.improve;
  const count = props.proposals.filter((p) => props.chosen[p.id] !== false).length;
  return (
    <div className="space-y-4">
      <h3 className={THEME_TOKENS.typography.panelTitle}>{c.proposalsTitle}</h3>
      {props.speakerWarning ? (
        <div className={cn(THEME_TOKENS.radius.control, "flex flex-wrap items-center justify-between gap-2 bg-warning/10 px-4 py-3")} role="status">
          <p className="text-[14px] text-foreground">{c.speakerWarning}</p>
          <Button type="button" variant="outline" size="sm" onClick={props.onSwap}>
            <Repeat2 aria-hidden strokeWidth={1.5} />
            {c.swapSpeakers}
          </Button>
        </div>
      ) : null}
      {props.proposals.length ? (
        <>
          <ul className="space-y-3">
            {props.proposals.map((proposal) => (
              <ProposalCard key={proposal.id} proposal={proposal} props={props} />
            ))}
          </ul>
          <Button type="button" disabled={count === 0 || props.applying} onClick={props.onApply}>
            {props.applying ? <VocifySpinner size={12} tone="onFill" /> : null}
            {props.applying ? c.proposalsApplying : c.proposalsApply.replace("{count}", String(count))}
          </Button>
        </>
      ) : (
        <p className={THEME_TOKENS.typography.body}>{c.proposalsNone}</p>
      )}
    </div>
  );
}
