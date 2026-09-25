import { ArrowSquareOut, ArrowUUpLeft, Phone, X } from "@phosphor-icons/react";
import { IconAction } from "@/components/ui/icon-action";
import { useLanguage } from "@/lib/i18n";

type Props = {
  onCall?: () => void;
  crmHref?: string | null;
  onDismiss?: () => void;
  onUndo?: () => void;
};

export function TodayCardActions({ onCall, crmHref, onDismiss, onUndo }: Props) {
  const { t } = useLanguage();
  return (
    <div className="flex items-center gap-0.5">
      {onCall ? (
        <IconAction label={t.product.today_call} onClick={onCall}>
          <Phone size={16} weight="light" />
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
            <ArrowSquareOut size={16} weight="light" />
          </span>
        </a>
      ) : null}
      {onDismiss ? (
        <IconAction label={t.product.dismiss} tone="danger" onClick={onDismiss}>
          <X size={16} weight="light" />
        </IconAction>
      ) : null}
      {onUndo ? (
        <IconAction label={t.product.undo} onClick={onUndo}>
          <ArrowUUpLeft size={16} weight="light" />
        </IconAction>
      ) : null}
    </div>
  );
}
