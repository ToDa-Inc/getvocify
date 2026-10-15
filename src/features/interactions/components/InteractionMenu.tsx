import { useState } from "react";
import { MoreHorizontal } from "lucide-react";
import { toast } from "sonner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { useDeleteMemo } from "@/features/memos";
import { useLanguage } from "@/lib/i18n";

/**
 * The row's three dots: open it, copy its link, delete it (only the person who recorded it can). Deleting asks first and
 * says what it does not touch, which is what the CRM already holds.
 */
export function InteractionMenu({ memoId, canDelete, onDeleted, visible = false }: { memoId: string; canDelete: boolean; onDeleted?: () => void; visible?: boolean }) {
  const { t } = useLanguage();
  const copy = t.product.interactions;
  const remove = useDeleteMemo();
  const [asking, setAsking] = useState(false);
  const link = `${window.location.origin}/dashboard/memos/${memoId}`;

  const copyLink = () => {
    void navigator.clipboard.writeText(link).then(
      () => toast.success(copy.linkCopied),
      () => toast.error(copy.deleteFailed),
    );
  };

  const confirm = () =>
    remove.mutate(memoId, {
      onSuccess: () => {
        setAsking(false);
        toast.success(copy.deleted);
        onDeleted?.();
      },
      onError: () => toast.error(copy.deleteFailed),
    });

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            aria-label={copy.menu}
            title={copy.menu}
            className={`flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground ${visible ? "" : "opacity-0 "}transition-opacity hover:bg-secondary hover:text-foreground focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring group-hover:opacity-100 data-[state=open]:opacity-100 motion-reduce:transition-none`}
          >
            <MoreHorizontal className="h-4 w-4" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={copyLink}>{copy.copyLink}</DropdownMenuItem>
          {canDelete ? (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem className="text-destructive focus:text-destructive" onSelect={() => setAsking(true)}>
                {copy.delete}
              </DropdownMenuItem>
            </>
          ) : null}
        </DropdownMenuContent>
      </DropdownMenu>
      <AlertDialog open={asking} onOpenChange={(open) => !remove.isPending && setAsking(open)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{copy.deleteTitle}</AlertDialogTitle>
            <AlertDialogDescription>{copy.deleteBody}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={remove.isPending}>{copy.deleteCancel}</AlertDialogCancel>
            <AlertDialogAction
              disabled={remove.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={(event) => {
                event.preventDefault();
                confirm();
              }}
            >
              {copy.deleteConfirm}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
