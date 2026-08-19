/**
 * CRM fill-policy labels for Settings field mapping.
 * Keep classification in lockstep with backend/app/services/extraction_policy.py.
 */

export type FillPolicy = "identity" | "strategy" | "research" | "call_note" | "explicit";

const IDENTITY_NAMES = new Set([
  "firstname",
  "lastname",
  "email",
  "first_name",
  "last_name",
  "hs_email",
]);
const IDENTITY_NAME_WRITE_KEYS = new Set([
  "firstname",
  "lastname",
  "first_name",
  "last_name",
  "FirstName",
  "LastName",
]);
const CALL_NOTE_NAMES = new Set(["description", "summary"]);

const STRATEGY_RE =
  /\b(call angle|outreach angle|talk track|talktrack|talking point|pre-?call|pre call|cadence|sequence message|outreach hook|angulo|ángulo)\b/i;
const STRATEGY_NAME_RE = /(angle|talk_?track|pre_?call|cadence)\b/i;
const RESEARCH_RE =
  /\b(sales motion|icp|persona|enrichment|fit score|account fit|encaje|icp fit|\bfit\b)\b/i;
const RESEARCH_NAME_RE = /(sales_?motion|\bfit\b|icp|persona|enrichment)/i;

export const FILL_POLICY_LABELS: Record<FillPolicy, string> = {
  identity: "Keep existing",
  strategy: "Never from calls",
  research: "Only if empty",
  call_note: "Call note",
  explicit: "From transcript",
};

function blob(spec: { name?: string; label?: string; description?: string }): string {
  return [spec.name || "", spec.label || "", spec.description || ""]
    .join(" ")
    .replace(/_/g, " ")
    .replace(/-/g, " ");
}

export function classifyFillPolicy(spec: {
  name?: string;
  label?: string;
  description?: string;
  fill_policy?: FillPolicy | null;
}): FillPolicy {
  if (spec.fill_policy) return spec.fill_policy;
  const name = String(spec.name || "").trim();
  const nameL = name.toLowerCase();
  if (CALL_NOTE_NAMES.has(nameL)) return "call_note";
  if (IDENTITY_NAMES.has(nameL) || IDENTITY_NAME_WRITE_KEYS.has(name)) return "identity";
  const text = blob(spec);
  const nameKey = name.replace(/-/g, "_");
  if (STRATEGY_RE.test(text) || STRATEGY_NAME_RE.test(nameKey)) return "strategy";
  if (RESEARCH_RE.test(text) || RESEARCH_NAME_RE.test(nameKey)) return "research";
  return "explicit";
}
