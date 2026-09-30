/** Query keys and fixed identifiers shared by the playbook screens. */

export const PLAYBOOKS_KEY = ["playbooks"] as const;
export const COMPANY_KEY = ["playbook-company"] as const;
export const CATALOG_KEY = ["playbooks-catalog"] as const;
export const DEAL_STAGES_KEY = ["playbooks-deal-stages"] as const;
export const QUALIFICATION_TEMPLATES_KEY = ["playbook-qualification-templates"] as const;
export const insightsKey = (motionKey: string) => ["playbook-insights", motionKey] as const;

/** The "Vuestra empresa" row, listed next to the call types' motion keys. */
export const COMPANY_ROW = "__company";
/** Always listed for a manager, so deleting one empties it rather than hiding it. */
export const BASE_KEYS: readonly string[] = ["discovery", "closing"];
/** The goal of the two base flows when the API sends none (motion.py GOAL_FOR_MOTION). */
export const DEFAULT_GOALS: Readonly<Record<string, string>> = { discovery: "meeting_booked", closing: "proposal_and_close" };
