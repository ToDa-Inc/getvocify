import { createElement, useEffect, useId } from "react";
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@/components/ui/dialog";
import { useLanguage } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const WISTIA_MEDIA_ID = import.meta.env.VITE_WISTIA_MEDIA_ID as string | undefined;

const WISTIA_PLAYER_SCRIPT = "https://fast.wistia.com/player.js";

function loadScriptOnce(src: string, options?: { type?: string }) {
  const existing = document.querySelector(`script[src="${src}"]`);
  if (existing) return Promise.resolve();
  return new Promise<void>((resolve, reject) => {
    const s = document.createElement("script");
    s.src = src;
    s.async = true;
    if (options?.type) s.type = options.type;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error(`Failed to load script: ${src}`));
    document.body.appendChild(s);
  });
}

type DemoVideoDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function DemoVideoDialog({ open, onOpenChange }: DemoVideoDialogProps) {
  const { t } = useLanguage();
  const id = WISTIA_MEDIA_ID?.trim();
  const titleId = useId();

  useEffect(() => {
    if (!open || !id) return;
    let cancelled = false;
    (async () => {
      try {
        await loadScriptOnce(WISTIA_PLAYER_SCRIPT);
        if (cancelled) return;
        await loadScriptOnce(`https://fast.wistia.com/embed/${id}.js`, { type: "module" });
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, id]);

  useEffect(() => {
    if (!open || !id) return;
    const styleId = `wistia-modal-placeholder-${id}`;
    if (document.getElementById(styleId)) return;
    const style = document.createElement("style");
    style.id = styleId;
    style.textContent = `
      wistia-player[media-id='${id}']:not(:defined) {
        background: center / contain no-repeat url('https://fast.wistia.com/embed/medias/${id}/swatch');
        display: block;
        filter: blur(5px);
        padding-top: 56.25%;
      }
    `;
    document.head.appendChild(style);
    return () => {
      document.getElementById(styleId)?.remove();
    };
  }, [open, id]);

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
        {open && id ? (
          <div className="w-full bg-black">
            {createElement("wistia-player", {
              "media-id": id,
              aspect: "1.7777777777777777",
            })}
          </div>
        ) : open && !id ? (
          <div className="p-8 text-center text-sm text-muted-foreground bg-background">
            {t.demo.configureEnv}
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
