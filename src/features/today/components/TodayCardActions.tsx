import { ExternalLink, Undo2, Phone, X } from "lucide-react";
import { IconAction } from "@/components/ui/icon-action";
import { useLanguage } from "@/lib/i18n";

type Props = {
  onCall?: () => void;
  callLabel?: string;
  crmHref?: string | null;
  onDismiss?: () => void;
  onUndo?: () => void;
};

export function TodayCardActions({ onCall, callLabel, crmHref, onDismiss, onUndo }: Props) {
  const { t } = useLanguage();
  return (
    <div className="flex items-center gap-0.5">
      {onCall ? (
        <IconAction label={callLabel ?? t.product.today_call} onClick={onCall}>
          <Phone size={16} strokeWidth={1.5} />
        </IconAction>
      ) : null}
      {crmHref ? (
        <a
          href={crmHref}
          target="_blank"
          rel="noreferrer"
          className="inline-flex"
          aria-label={t.product.today_open}
        >
          <span className="inline-flex h-9 w-9 items-center justify-center rounded-full text-muted-foreground hover:bg-secondary/60 hover:text-foreground">
            <ExternalLink size={16} strokeWidth={1.5} />
          </span>
        </a>
      ) : null}
      {onDismiss ? (
        <IconAction label={t.product.dismiss} tone="danger" onClick={onDismiss}>
          <X size={16} strokeWidth={1.5} />
        </IconAction>
      ) : null}
      {onUndo ? (
        <IconAction label={t.product.undo} onClick={onUndo}>
          <Undo2 size={16} strokeWidth={1.5} />
        </IconAction>
      ) : null}
    </div>
  );
}
