import { useCallback, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/features/auth";
import { authKeys } from "@/features/auth/api";
import {
  billingApi,
  billingKeys,
  type BillingInterval,
  type BillingPlan,
  type PlanId,
} from "@/features/billing/api";
import { companyKeys } from "@/features/company/api";
import { yearlyDiscountPercent } from "@/lib/billing-access";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { StripeCheckoutPanel } from "@/components/billing/StripeCheckoutPanel";
import { Button } from "@/components/ui/button";
import { VocifyLoader, VocifySpinner } from "@/components/ui/vocify-loader";

const RETURN_PATH = "/dashboard/settings/billing";

function apiErrorMessage(error: unknown, fallback: string) {
  if (error && typeof error === "object" && "data" in error) {
    const detail = (error as { data?: { detail?: unknown } }).data?.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

function planLabel(plan: PlanId) {
  return plan === "pro" ? "Pro" : "Starter";
}

function priceLabelFor(plan: BillingPlan, interval: BillingInterval) {
  if (interval === "yearly") {
    return `€${plan.yearlyMonthlyAmount} / month · €${plan.yearlyAmount} yearly`;
  }
  return `€${plan.monthlyAmount} / month`;
}

const BillingPage = () => {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const canManage = user?.company?.role === "owner" || user?.company?.role === "admin";

  const { data, isLoading } = useQuery({
    queryKey: billingKeys.status(),
    queryFn: () => billingApi.status(),
  });

  const [interval, setInterval] = useState<BillingInterval>("yearly");
  const [checkout, setCheckout] = useState<{
    plan: PlanId;
    planName: string;
    priceLabel: string;
    clientSecret: string | null;
  } | null>(null);

  useEffect(() => {
    if (data?.billingInterval === "monthly" || data?.billingInterval === "yearly") {
      setInterval(data.billingInterval);
    }
  }, [data]);

  const refreshBilling = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: billingKeys.all });
    queryClient.invalidateQueries({ queryKey: companyKeys.all });
    queryClient.invalidateQueries({ queryKey: authKeys.me() });
  }, [queryClient]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const billing = params.get("billing");
    if (!billing) return;
    if (billing === "success") {
      toast.success("You're in. Welcome.");
      setCheckout(null);
    }
    if (billing === "cancel") toast.message("Checkout left unfinished.");
    window.history.replaceState({}, "", window.location.pathname);
    refreshBilling();
  }, [refreshBilling]);

  const checkoutMutation = useMutation({
    mutationFn: (plan: PlanId) =>
      billingApi.checkout({
        plan,
        interval,
        returnUrl: `${window.location.origin}${RETURN_PATH}`,
      }),
    onSuccess: (res, plan) => {
      if (res.action === "checkout") {
        const selected = data?.plans.find((item) => item.id === plan);
        if (res.clientSecret && data?.publishableKey && selected) {
          setCheckout({
            plan,
            planName: selected.name,
            priceLabel: priceLabelFor(selected, interval),
            clientSecret: res.clientSecret,
          });
          return;
        }
        if (res.checkoutUrl) {
          window.location.href = res.checkoutUrl;
          return;
        }
        toast.error("Could not open checkout");
        setCheckout(null);
        return;
      }
      setCheckout(null);
      refreshBilling();
      toast.success(`You're on ${planLabel(plan)}.`);
    },
    onError: (error) => {
      setCheckout(null);
      toast.error(apiErrorMessage(error, "Could not start checkout"));
    },
  });

  const portalMutation = useMutation({
    mutationFn: () => billingApi.portal(`${window.location.origin}${RETURN_PATH}`),
    onSuccess: (url) => {
      if (url) window.location.href = url;
    },
    onError: (error) => {
      toast.error(apiErrorMessage(error, "Could not open billing portal"));
    },
  });

  const handleCheckoutComplete = useCallback(() => {
    setCheckout(null);
    refreshBilling();
    toast.success("You're in. Welcome.");
  }, [refreshBilling]);

  if (isLoading || !data) {
    return (
      <div className={THEME_TOKENS.interaction.pageLoad}>
        <VocifyLoader size="lg" label="Loading billing..." />
      </div>
    );
  }

  const locked = data.paywalled;
  const pendingPlan = checkoutMutation.isPending ? checkoutMutation.variables : null;
  const yearlySave = Math.max(
    data.yearlyDiscountPercent,
    ...data.plans.map((plan) =>
      plan.yearlyDiscountPercent || yearlyDiscountPercent(plan.monthlyAmount, plan.yearlyAmount),
    ),
  );

  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <p className={THEME_TOKENS.typography.capsLabel}>
          {locked ? "Workspace locked" : "Plans"}
        </p>
        <h2 className={`${THEME_TOKENS.typography.editorialHeader} text-[1.75rem] md:text-[2rem] text-foreground`}>
          {locked ? "Unlock the workspace." : "Choose how you sell."}
        </h2>
        <p className={THEME_TOKENS.typography.body}>
          {locked
            ? "Starter captures the call. Pro puts you on the line."
            : "The same craft on both plans. Pro includes the dialer."}
        </p>
        {data.currentPeriodEnd ? (
          <p className="text-xs text-muted-foreground pt-1">
            {data.planType ? `${planLabel(data.planType)} · ` : ""}
            {data.cancelAtPeriodEnd ? "Cancels" : "Renews"}{" "}
            {new Date(data.currentPeriodEnd).toLocaleDateString()}
          </p>
        ) : null}
        {canManage && data.configured && (
          <div className="flex flex-wrap items-center gap-3 pt-2">
            <div className="inline-flex items-center rounded-full border border-border/40 bg-secondary/5 p-1">
              {(
                [
                  { value: "monthly" as const, label: "Monthly" },
                  { value: "yearly" as const, label: "Yearly" },
                ]
              ).map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setInterval(option.value)}
                  className={`inline-flex items-center rounded-full px-4 h-8 text-xs font-medium transition-colors ${
                    interval === option.value
                      ? "bg-beige text-cream"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {option.label}
                  {option.value === "yearly" && yearlySave > 0 && (
                    <span
                      className={`ml-1.5 rounded-full px-1.5 py-0.5 text-[10px] leading-none ${
                        interval === "yearly" ? "bg-cream/20 text-cream" : "bg-beige/15 text-beige"
                      }`}
                    >
                      −{yearlySave}%
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {!data.configured && (
        <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-5`}>
          <p className="text-sm text-muted-foreground">
            Billing is not live on this environment yet. A Vocify admin can still unlock the workspace.
          </p>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {data.plans.map((plan) => {
          const isYearly = interval === "yearly";
          const isCurrent =
            data.hasSubscription &&
            data.planType === plan.id &&
            data.billingInterval === interval;
          const highlighted = plan.id === "pro";
          const discount = plan.yearlyDiscountPercent;

          return (
            <div
              key={plan.id}
              className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6 md:p-7 space-y-5 ${
                highlighted ? "border-beige/40" : ""
              }`}
            >
              <div className="space-y-1.5">
                <div className="flex items-center justify-between gap-3">
                  <p className={THEME_TOKENS.typography.sectionTitle}>{plan.name}</p>
                  {isCurrent ? (
                    <span className="text-[11px] text-beige">Current</span>
                  ) : highlighted ? (
                    <span className="text-[11px] text-beige">Includes the dialer</span>
                  ) : null}
                </div>
                <p className="text-sm text-muted-foreground">{plan.tagline}</p>
              </div>

              {isYearly ? (
                <div className="space-y-2">
                  <div className="flex flex-wrap items-end gap-2.5">
                    <p className="text-[2rem] leading-none tracking-tight text-foreground">
                      €{plan.yearlyMonthlyAmount}
                      <span className="text-sm text-muted-foreground font-normal"> / month</span>
                    </p>
                    <span className="mb-0.5 text-sm text-muted-foreground line-through">
                      €{plan.monthlyAmount}
                    </span>
                    {discount > 0 && (
                      <span className="mb-0.5 rounded-full bg-beige/15 px-2 py-0.5 text-[11px] text-beige">
                        −{discount}%
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground">€{plan.yearlyAmount} billed yearly</p>
                </div>
              ) : (
                <p className="text-[2rem] leading-none tracking-tight text-foreground">
                  €{plan.monthlyAmount}
                  <span className="text-sm text-muted-foreground font-normal"> / month</span>
                </p>
              )}

              <ul className="space-y-2">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex items-start gap-2 text-sm text-foreground">
                    <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-beige" />
                    <span>{feature}</span>
                  </li>
                ))}
              </ul>

              {canManage && data.configured && (
                <Button
                  disabled={checkoutMutation.isPending || isCurrent}
                  onClick={() => {
                    if (!isCurrent) {
                      setCheckout({
                        plan: plan.id,
                        planName: plan.name,
                        priceLabel: priceLabelFor(plan, interval),
                        clientSecret: null,
                      });
                      checkoutMutation.mutate(plan.id);
                    }
                  }}
                  className={`w-full rounded-full h-11 ${
                    highlighted
                      ? "bg-beige text-cream hover:bg-beige-dark"
                      : "bg-secondary/20 text-foreground hover:bg-secondary/30"
                  }`}
                >
                  {pendingPlan === plan.id ? (
                    <>
                      <VocifySpinner size={12} />
                      Working…
                    </>
                  ) : isCurrent ? (
                    "Current plan"
                  ) : data.hasSubscription ? (
                    `Switch to ${plan.name}`
                  ) : (
                    `Continue with ${plan.name}`
                  )}
                </Button>
              )}
            </div>
          );
        })}
      </div>

      {canManage && data.hasSubscription && (
        <div className="flex justify-center">
          <Button
            variant="outline"
            disabled={portalMutation.isPending}
            onClick={() => portalMutation.mutate()}
            className="rounded-full h-11"
          >
            Manage payment method
          </Button>
        </div>
      )}

      {!canManage && (
        <p className="text-sm text-muted-foreground text-center">
          Ask an owner or admin to choose a plan.
        </p>
      )}

      {data.publishableKey && (
        <StripeCheckoutPanel
          open={Boolean(checkout)}
          onClose={() => {
            setCheckout(null);
            checkoutMutation.reset();
          }}
          onComplete={handleCheckoutComplete}
          publishableKey={data.publishableKey}
          clientSecret={checkout?.clientSecret ?? null}
          loading={checkoutMutation.isPending || Boolean(checkout && !checkout.clientSecret)}
          planName={checkout ? `${checkout.planName} plan` : "Checkout"}
          priceLabel={checkout?.priceLabel ?? ""}
        />
      )}
    </div>
  );
};

export default BillingPage;
