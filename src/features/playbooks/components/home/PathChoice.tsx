import { ArrowRight, FileUp, Files, MessagesSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useLanguage } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export type ContentPath = "all" | "upload" | "ask";

/**
 * "¿Cómo quieres darnos el contenido?": the three ways to fill the interactions just defined. One document for all of them,
 * a document per interaction, or answering questions so Vocify builds it. Each is a plain outlined row, nothing more.
 */
export function PathChoice({ askAvailable, onChoose, onLater }: { askAvailable: boolean; onChoose: (path: ContentPath) => void; onLater: () => void }) {
  const { t } = useLanguage();
  const c = t.product.pb2.home;
  const options: { path: ContentPath; title: string; lead: string; Icon: typeof FileUp }[] = [
    { path: "all", title: c.pathAll, lead: c.pathAllLead, Icon: FileUp },
    { path: "upload", title: c.pathUpload, lead: c.pathUploadLead, Icon: Files },
    ...(askAvailable ? [{ path: "ask" as const, title: c.pathAsk, lead: c.pathAskLead, Icon: MessagesSquare }] : []),
  ];
  return (
    <div className="space-y-6">
      <ul className="space-y-3">
        {options.map(({ path, title, lead, Icon }) => (
          <li key={path}>
            <button
              type="button"
              onClick={() => onChoose(path)}
              className={cn(
                "group flex w-full items-center gap-4 rounded-2xl border border-border/80 px-5 py-4 text-left transition-colors duration-150 motion-reduce:transition-none",
                "hover:border-beige/50 hover:bg-secondary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              )}
            >
              <Icon aria-hidden className="h-5 w-5 shrink-0 text-muted-foreground" strokeWidth={1.5} />
              <span className="min-w-0 flex-1 space-y-0.5">
                <span className="block text-[15px] font-medium text-foreground">{title}</span>
                <span className="block text-[13px] leading-snug text-muted-foreground">{lead}</span>
              </span>
              <ArrowRight aria-hidden className="h-4 w-4 shrink-0 text-muted-foreground/60 transition-transform duration-150 group-hover:translate-x-0.5 motion-reduce:transition-none" strokeWidth={1.5} />
            </button>
          </li>
        ))}
      </ul>
      <Button type="button" variant="quiet" size="text" onClick={onLater}>
        {c.later}
      </Button>
    </div>
  );
}
