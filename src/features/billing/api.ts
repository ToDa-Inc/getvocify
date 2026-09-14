import { api } from "@/shared/lib/api-client";
import { yearlyDiscountPercent, yearlyMonthlyAmount } from "@/lib/billing-access";

export type PlanId = "starter" | "pro";
export type BillingInterval = "monthly" | "yearly";

export type BillingPlan = {
  id: PlanId;
  name: string;
  tagline: string;
  monthlyAmount: number;
  yearlyAmount: number;
  yearlyMonthlyAmount: number;
  yearlyDiscountPercent: number;
  features: string[];
  includesDialer: boolean;
  dialerMinutes: number | null;
};

export type BillingStatus = {
  configured: boolean;
  publishableKey: string | null;
  accessMode: string;
  billingStatus: string;
  planType: PlanId | null;
  billingInterval: BillingInterval | null;
  currentPeriodEnd: string | null;
  cancelAtPeriodEnd: boolean;
  seatLimit: number;
  seatsUsed: number;
  paywalled: boolean;
  canManage: boolean;
  canUseDialer: boolean;
  hasSubscription: boolean;
  currency: string;
  yearlyDiscountPercent: number;
  plans: BillingPlan[];
};

export const FALLBACK_PLANS: BillingPlan[] = [
  {
    id: "starter",
    name: "Starter",
    tagline: "Every conversation, captured and closed.",
    monthlyAmount: 39,
    yearlyAmount: 390,
    yearlyMonthlyAmount: 33,
    yearlyDiscountPercent: 17,
    features: [
      "Transcriptions, word-perfect",
      "Summaries that land",
      "CRM that writes itself",
      "Tasks, already queued",
      "Follow-ups, ready to send",
      "Scoring you can stand on",
      "Coaching as it happens",
    ],
    includesDialer: false,
    dialerMinutes: null,
  },
  {
    id: "pro",
    name: "Pro",
    tagline: "The same craft, plus a dialer that goes the distance.",
    monthlyAmount: 59,
    yearlyAmount: 590,
    yearlyMonthlyAmount: 49,
    yearlyDiscountPercent: 17,
    features: [
      "Transcriptions, word-perfect",
      "Summaries that land",
      "CRM that writes itself",
      "Tasks, already queued",
      "Follow-ups, ready to send",
      "Scoring you can stand on",
      "Coaching as it happens",
      "Dialer included — 1,000 minutes",
    ],
    includesDialer: true,
    dialerMinutes: 1000,
  },
];

export const billingKeys = {
  all: ["billing"] as const,
  status: () => [...billingKeys.all, "status"] as const,
};

function mapPlan(raw: Record<string, unknown>): BillingPlan {
  const monthlyAmount = Number(raw.monthly_amount ?? 0);
  const yearlyAmount = Number(raw.yearly_amount ?? 0);
  return {
    id: raw.id === "pro" ? "pro" : "starter",
    name: String(raw.name ?? ""),
    tagline: String(raw.tagline ?? ""),
    monthlyAmount,
    yearlyAmount,
    yearlyMonthlyAmount:
      raw.yearly_monthly_amount != null
        ? Number(raw.yearly_monthly_amount)
        : yearlyMonthlyAmount(yearlyAmount),
    yearlyDiscountPercent:
      raw.yearly_discount_percent != null
        ? Number(raw.yearly_discount_percent)
        : yearlyDiscountPercent(monthlyAmount, yearlyAmount),
    features: Array.isArray(raw.features) ? raw.features.map(String) : [],
    includesDialer: Boolean(raw.includes_dialer),
    dialerMinutes: raw.dialer_minutes != null ? Number(raw.dialer_minutes) : null,
  };
}

function mapStatus(raw: Record<string, unknown>): BillingStatus {
  const planType = raw.plan_type === "starter" || raw.plan_type === "pro" ? raw.plan_type : null;
  const interval =
    raw.billing_interval === "monthly" || raw.billing_interval === "yearly"
      ? raw.billing_interval
      : null;
  const plans = Array.isArray(raw.plans) ? raw.plans.map((p) => mapPlan(p as Record<string, unknown>)) : [];
  return {
    configured: Boolean(raw.configured),
    publishableKey: typeof raw.publishable_key === "string" && raw.publishable_key ? raw.publishable_key : null,
    accessMode: String(raw.access_mode ?? "open"),
    billingStatus: String(raw.billing_status ?? "none"),
    planType,
    billingInterval: interval,
    currentPeriodEnd: (raw.current_period_end as string) ?? null,
    cancelAtPeriodEnd: Boolean(raw.cancel_at_period_end),
    seatLimit: Number(raw.seat_limit ?? 1),
    seatsUsed: Number(raw.seats_used ?? 0),
    paywalled: Boolean(raw.paywalled),
    canManage: Boolean(raw.can_manage),
    canUseDialer: raw.can_use_dialer == null ? true : Boolean(raw.can_use_dialer),
    hasSubscription: Boolean(raw.has_subscription),
    currency: String(raw.currency ?? "eur"),
    yearlyDiscountPercent: Number(raw.yearly_discount_percent ?? 17),
    plans: plans.length ? plans : FALLBACK_PLANS,
  };
}

export const billingApi = {
  status: async (): Promise<BillingStatus> => {
    const raw = await api.get<Record<string, unknown>>("/billing/status");
    return mapStatus(raw);
  },

  checkout: async (body: {
    plan: PlanId;
    interval: BillingInterval;
    returnUrl: string;
  }): Promise<{
    action: "checkout" | "updated";
    checkoutUrl?: string;
    clientSecret?: string;
    planType?: PlanId;
  }> => {
    const raw = await api.post<Record<string, unknown>>("/billing/checkout", {
      plan: body.plan,
      interval: body.interval,
      return_url: body.returnUrl,
    });
    return {
      action: raw.action === "updated" ? "updated" : "checkout",
      checkoutUrl: (raw.checkout_url as string) ?? undefined,
      clientSecret: (raw.client_secret as string) ?? undefined,
      planType: raw.plan_type === "starter" || raw.plan_type === "pro" ? raw.plan_type : undefined,
    };
  },

  portal: async (returnUrl: string): Promise<string> => {
    const raw = await api.post<Record<string, unknown>>("/billing/portal", {
      return_url: returnUrl,
    });
    return String(raw.portal_url ?? "");
  },
};
