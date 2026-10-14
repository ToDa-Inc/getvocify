import { useId } from "react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { useLanguage } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/** The Vocify launch film (Captura, Automatiza, Asiste, Aprende), web-sized copy in /public/demo. */
const VIDEO_SRC = "/demo/vocify-launch.mp4";
const VIDEO_POSTER = "/demo/vocify-launch-poster.jpg";

type DemoVideoDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function DemoVideoDialog({ open, onOpenChange }: DemoVideoDialogProps) {
  const { t } = useLanguage();
  const titleId = useId();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        aria-labelledby={titleId}
        className={cn(
          "max-w-4xl w-[min(100vw-2rem,56rem)] translate-x-[-50%] translate-y-[-50%] gap-0 border-none bg-black p-0 sm:rounded-2xl overflow-hidden shadow-2xl",
          "data-[state=open]:animate-in data-[state=closed]:animate-out",
          "[&>button]:text-white [&>button]:opacity-90 [&>button]:hover:opacity-100 [&>button]:hover:bg-white/15 [&>button]:ring-offset-black",
        )}
      >
        <DialogTitle id={titleId} className="sr-only">
          {t.demo.title}
        </DialogTitle>
        {open ? (
          <video
            className="aspect-video w-full bg-black"
            src={VIDEO_SRC}
            poster={VIDEO_POSTER}
            controls
            autoPlay
            playsInline
            preload="metadata"
          />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
