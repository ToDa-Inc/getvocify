import { companyCanUseDialer, companyIsPaywalled, type BillingCompany } from "./billing-access.ts";

/** A contact get_call_priorities returned for this turn. The server builds it; the model's text never does. */
export type AskCallTarget = {
  contact_id: string;
  connection_id?: string | null;
  provider?: string | null;
  contact_name?: string | null;
  reason: string;
  next_action?: string | null;
  crm_url?: string | null;
};

const MAX_TARGETS = 5;

export function askCallTargets(turn: { call_targets?: AskCallTarget[] | null }): AskCallTarget[] {
  const rows = turn.call_targets;
  if (!rows?.length) return [];
  return rows
    .filter((row) => Boolean(row.contact_id?.trim() && row.reason?.trim()))
    .slice(0, MAX_TARGETS)
    .map((row) => ({ ...row, crm_url: row.crm_url?.startsWith("https://") ? row.crm_url : null }));
}

/** Same rule the dashboard uses to mount the dialer. */
export function dialerAvailable(input: { desktop: boolean; company?: BillingCompany | null }): boolean {
  return !input.desktop && !companyIsPaywalled(input.company) && companyCanUseDialer(input.company);
}
