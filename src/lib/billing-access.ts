export type AccessMode = "open" | "paywalled" | "unlocked";
export type BillingStatus =
  | "none"
  | "active"
  | "trialing"
  | "past_due"
  | "canceled"
  | "unpaid"
  | "incomplete";
export type PlanType = "starter" | "pro";

export type BillingCompany = {
  accessMode?: AccessMode | string | null;
  billingStatus?: BillingStatus | string | null;
  planType?: PlanType | string | null;
  paywalled?: boolean;
  canUseDialer?: boolean;
};

const PAID = new Set(["active", "trialing"]);

export function companyIsPaywalled(company?: BillingCompany | null): boolean {
  if (!company) return false;
  if (typeof company.paywalled === "boolean") return company.paywalled;
  if ((company.accessMode || "open") !== "paywalled") return false;
  return !PAID.has(String(company.billingStatus || "none"));
}

export function yearlyDiscountPercent(monthly: number, yearly: number): number {
  const full = monthly * 12;
  if (full <= 0) return 0;
  return Math.max(0, Math.round(((full - yearly) / full) * 100));
}

export function yearlyMonthlyAmount(yearly: number): number {
  return Math.round(yearly / 12);
}

export function companyCanUseDialer(company?: BillingCompany | null): boolean {
  if (!company) return true;
  if (typeof company.canUseDialer === "boolean") return company.canUseDialer;
  if ((company.accessMode || "open") === "unlocked") return true;
  const paid = PAID.has(String(company.billingStatus || "none"));
  if (paid) return company.planType === "pro";
  return (company.accessMode || "open") === "open";
}
