import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { VocifySpinner } from "@/components/ui/vocify-loader";

type ConfirmActionProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: "default" | "danger";
  pending?: boolean;
  onConfirm: () => void;
};

/** Vocify confirm sheet. Recycle for delete, disconnect, revoke, and similar irreversible actions. */
export function ConfirmAction({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  tone = "danger",
  pending = false,
  onConfirm,
}: ConfirmActionProps) {
  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (pending) return;
        onOpenChange(next);
      }}
    >
      <AlertDialogContent
        className={cn(
          THEME_TOKENS.radius.container,
          "max-w-md gap-6 border-border/70 bg-card p-6 md:p-8",
        )}
      >
        <AlertDialogHeader className="space-y-2 text-left">
          <AlertDialogTitle className={THEME_TOKENS.typography.sectionTitle}>{title}</AlertDialogTitle>
          <AlertDialogDescription className="text-sm leading-relaxed text-muted-foreground">
            {description}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter className="gap-2 sm:justify-end">
          <AlertDialogCancel
            disabled={pending}
            className="mt-0 h-10 rounded-full px-5"
          >
            {cancelLabel}
          </AlertDialogCancel>
          <button
            type="button"
            disabled={pending}
            onClick={onConfirm}
            className={cn(
              "inline-flex h-10 items-center justify-center gap-2 rounded-full px-5 text-sm disabled:opacity-50",
              THEME_TOKENS.motion.tapScale,
              tone === "danger"
                ? "bg-destructive text-destructive-foreground hover:bg-destructive/90"
                : "bg-beige text-cream hover:bg-beige-dark",
            )}
          >
            {pending ? <VocifySpinner size={12} /> : null}
            {pending ? "Working…" : confirmLabel}
          </button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
