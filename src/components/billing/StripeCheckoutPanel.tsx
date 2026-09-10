import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { loadStripe, type Stripe } from "@stripe/stripe-js";
import { X } from "lucide-react";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { VocifyLoader } from "@/components/ui/vocify-loader";

type Props = {
  open: boolean;
  onClose: () => void;
  onComplete?: () => void;
  publishableKey: string;
  clientSecret: string | null;
  loading?: boolean;
  planName: string;
  priceLabel: string;
};

let stripePromise: Promise<Stripe | null> | null = null;

function stripeFor(key: string) {
  if (!stripePromise) {
    stripePromise = loadStripe(key);
  }
  return stripePromise;
}

export function StripeCheckoutPanel({
  open,
  onClose,
  onComplete,
  publishableKey,
  clientSecret,
  loading = false,
  planName,
  priceLabel,
}: Props) {
  const mountRef = useRef<HTMLDivElement>(null);
  const checkoutRef = useRef<{ destroy: () => Promise<void> | void; unmount?: () => void } | null>(null);
  const [mountError, setMountError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  useEffect(() => {
    if (!open || !clientSecret || !publishableKey) return;
    let cancelled = false;
    const timers: number[] = [];

    const start = async () => {
      setMountError(null);
      const stripe = await stripeFor(publishableKey);
      if (cancelled || !stripe || !mountRef.current) return;
      if (checkoutRef.current) {
        try {
          await checkoutRef.current.destroy();
        } catch {
          checkoutRef.current.unmount?.();
        }
        checkoutRef.current = null;
      }
      mountRef.current.innerHTML = "";
      try {
        const checkout = await stripe.initEmbeddedCheckout({
          clientSecret,
          onComplete: () => {
            onComplete?.();
          },
        });
        if (cancelled) {
          await checkout.destroy();
          return;
        }
        checkoutRef.current = checkout;
        checkout.mount(mountRef.current);
        const scroller = mountRef.current.parentElement;
        const pinTop = () => {
          if (!cancelled && scroller) scroller.scrollTop = 0;
        };
        pinTop();
        requestAnimationFrame(pinTop);
        timers.push(window.setTimeout(pinTop, 200), window.setTimeout(pinTop, 500));
      } catch (error) {
        if (!cancelled) {
          setMountError(error instanceof Error ? error.message : "Could not open checkout");
        }
      }
    };

    void start();
    return () => {
      cancelled = true;
      timers.forEach((id) => window.clearTimeout(id));
      const current = checkoutRef.current;
      checkoutRef.current = null;
      if (current) {
        Promise.resolve(current.destroy()).catch(() => current.unmount?.());
      }
    };
  }, [open, clientSecret, publishableKey, onComplete]);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-[100]">
      <button
        type="button"
        aria-label="Close checkout"
        className="absolute inset-0 bg-black/50"
        onClick={onClose}
      />
      <aside
        className={`absolute inset-y-0 right-0 flex w-full max-w-[540px] flex-col border-l border-border bg-background shadow-2xl sm:inset-3 sm:left-auto sm:border ${THEME_TOKENS.radius.container} overflow-hidden`}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-border/60 px-5 py-4">
          <div>
            <p className={THEME_TOKENS.typography.sectionTitle}>{planName}</p>
            <p className="mt-1 text-sm text-muted-foreground">{priceLabel}</p>
          </div>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            className={THEME_TOKENS.interaction.iconButton}
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
          {mountError ? (
            <p className="p-5 text-sm text-destructive">{mountError}</p>
          ) : loading || !clientSecret ? (
            <div className="flex min-h-[320px] items-center justify-center">
              <VocifyLoader size="lg" label="Opening checkout..." />
            </div>
          ) : (
            <div ref={mountRef} className="min-h-full" />
          )}
        </div>
      </aside>
    </div>,
    document.body,
  );
}
