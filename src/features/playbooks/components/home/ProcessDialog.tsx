import { useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { GapAssistant } from "@/features/playbooks/components/GapAssistant";
import { IntakePanel } from "@/features/playbooks/components/IntakePanel";
import { PathChoice, type ContentPath } from "@/features/playbooks/components/home/PathChoice";
import { UnderstoodSummary } from "@/features/playbooks/components/UnderstoodSummary";
import type { Intake } from "@/features/playbooks/hooks/useIntake";
import { SalesProcessEditor } from "@/features/sales-process/SalesProcessEditor";
import { useLanguage } from "@/lib/i18n";

type Step = "define" | "path" | "all" | "ask";

/**
 * The window to create or edit the interactions, over the Playbook page. Step one defines them (name, goal, description,
 * order); when it is the first time, step two offers the three ways to give their content: one whole document, a document per
 * interaction, or answering questions with Vocify. Nothing leaves the page.
 */
export function ProcessDialog({
  open,
  onOpenChange,
  kind,
  first,
  intake,
  assistantOn,
  firstEmptyKey,
  name,
  onChanged,
  onOpenType,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  kind: "funnel" | "other";
  /** Nothing defined yet: after saving, offer the three ways to fill it in. */
  first: boolean;
  intake: Intake;
  assistantOn: boolean;
  /** The first interaction of the funnel that has nothing written, for "one document per interaction". */
  firstEmptyKey: string | null;
  name: (key: string) => string;
  onChanged: () => void;
  onOpenType: (key: string) => void;
}) {
  const { t } = useLanguage();
  const c = t.product.pb2.home;
  const [step, setStep] = useState<Step>("define");
  useEffect(() => {
    if (open) setStep("define");
  }, [open]);
  const close = () => onOpenChange(false);
  const title =
    step === "define" ? (kind === "funnel" ? c.processDialogTitle : c.otherDialogTitle) : step === "path" ? c.pathTitle : step === "all" ? c.pathAll : c.pathAsk;
  const lead = step === "define" ? (kind === "funnel" ? c.processDialogLead : t.product.pb2.process.otherLead) : step === "path" ? c.pathLead : "";

  const choose = (path: ContentPath) => {
    if (path === "upload") {
      close();
      if (firstEmptyKey) onOpenType(firstEmptyKey);
    } else setStep(path);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-2xl gap-6 overflow-y-auto rounded-2xl border-border/70 bg-background p-6 shadow-none sm:rounded-2xl md:p-8">
        <DialogHeader className="space-y-2 text-left">
          <DialogTitle className="text-[22px] font-semibold tracking-[-0.015em] text-foreground">{title}</DialogTitle>
          {lead ? <DialogDescription className="text-[15px] leading-relaxed text-muted-foreground">{lead}</DialogDescription> : <DialogDescription className="sr-only">{title}</DialogDescription>}
        </DialogHeader>
        {step === "define" ? (
          <SalesProcessEditor
            bare
            kind={kind}
            first={first}
            onCancel={close}
            onSaved={() => {
              onChanged();
              if (kind === "funnel" && first) setStep("path");
              else close();
            }}
          />
        ) : null}
        {step === "path" ? <PathChoice askAvailable={assistantOn} onChoose={choose} onLater={close} /> : null}
        {step === "all" ? (
          <div className="space-y-5">
            <Button type="button" variant="quiet" size="text" className="-ml-1" onClick={() => setStep("path")}>
              <ArrowLeft aria-hidden strokeWidth={1.5} />
              {c.back}
            </Button>
            {intake.understood ? (
              <UnderstoodSummary
                summary={intake.understood.summary}
                failed={intake.understood.failed}
                conflicts={intake.understood.conflicts}
                readError={(code) => (code && t.product.pb2.readErrors[code]) || ""}
                onNext={() => {
                  intake.clearUnderstood();
                  onChanged();
                  setStep(assistantOn ? "ask" : "path");
                }}
                onLater={() => {
                  intake.clearUnderstood();
                  onChanged();
                  close();
                }}
              />
            ) : (
              <IntakePanel intake={intake} alone={false} name={name} onTemplate={() => undefined} assistant={assistantOn} />
            )}
          </div>
        ) : null}
        {step === "ask" ? (
          <div className="space-y-5">
            <Button type="button" variant="quiet" size="text" className="-ml-1" onClick={() => setStep("path")}>
              <ArrowLeft aria-hidden strokeWidth={1.5} />
              {c.back}
            </Button>
            <GapAssistant motionKey={null} onChanged={onChanged} onTry={close} onBack={close} />
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
