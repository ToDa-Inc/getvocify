/**
 * Per-review omit of proposed CRM fields.
 * Keep in lockstep with chrome-extension/lib/extraction-omit.js.
 */

export type ProposedUpdate = {
  field_name?: string;
  field_label?: string;
  field_type?: string;
  object_type?: string;
  new_value?: string | number | null;
  current_value?: string | number | null;
  options?: unknown[];
};

export type ExtractionRecord = Record<string, unknown> & {
  raw_extraction?: Record<string, unknown>;
  contactName?: unknown;
  companyName?: unknown;
  contactPhone?: unknown;
  contactEmail?: unknown;
  contactRole?: unknown;
  dealAmount?: unknown;
  closeDate?: unknown;
  dealStage?: unknown;
  summary?: unknown;
  nextSteps?: unknown;
};

export function isInsightsField(fieldName: string | undefined): boolean {
  return (
    fieldName === "description" ||
    fieldName === "hs_next_step" ||
    String(fieldName || "").startsWith("next_step_task_")
  );
}

const IDENTITY_LABELS = new Set(["contact_name", "company_name", "dealname"]);

export function proposedFieldKey(update: ProposedUpdate | null | undefined): string | null {
  if (!update?.field_name) return null;
  return `${update.object_type || "deals"}:${update.field_name}`;
}

export function canEditOrRemoveProposedField(update: ProposedUpdate | null | undefined): boolean {
  if (!update?.field_name) return false;
  if (IDENTITY_LABELS.has(update.field_name)) return false;
  if (isInsightsField(update.field_name)) return false;
  if (update.object_type === "line_items") return false;
  if (String(update.field_name).startsWith("line_item_")) return false;
  const objectType = update.object_type || "deals";
  return objectType === "deals" || objectType === "contacts" || objectType === "companies";
}

const CONTACT_IDENTITY_TOP: Record<string, string[]> = {
  phone: ["contactPhone"],
  email: ["contactEmail"],
  jobtitle: ["contactRole"],
  firstname: ["contactName"],
  lastname: ["contactName"],
};

const COMPANY_IDENTITY_TOP: Record<string, string[]> = {
  name: ["companyName"],
};

const DEAL_IDENTITY_TOP: Record<string, string[]> = {
  amount: ["dealAmount"],
  Amount: ["dealAmount"],
  closedate: ["closeDate"],
  CloseDate: ["closeDate"],
  dealstage: ["dealStage"],
  StageName: ["dealStage"],
};

const DEAL_RAW_ALIASES: Record<string, string[]> = {
  amount: ["amount", "Amount"],
  Amount: ["amount", "Amount"],
  closedate: ["closedate", "CloseDate"],
  CloseDate: ["closedate", "CloseDate"],
  dealstage: ["dealstage", "StageName"],
  StageName: ["dealstage", "StageName"],
};

function cloneExtraction(extraction: ExtractionRecord | null | undefined): ExtractionRecord {
  const result: ExtractionRecord = { ...(extraction || {}) };
  const raw = {
    ...(result.raw_extraction && typeof result.raw_extraction === "object" ? result.raw_extraction : {}),
  };
  result.raw_extraction = raw;
  return result;
}

function nestedBag(raw: Record<string, unknown>, key: string): Record<string, unknown> {
  const bag = raw[key];
  return { ...(bag && typeof bag === "object" ? (bag as Record<string, unknown>) : {}) };
}

function parseFlexibleDateToIso(val: unknown): string | null {
  if (val == null || val === "") return null;
  const s = String(val).trim();
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) return s.slice(0, 10);
  return s;
}

export function applyProposedUpdates(
  extraction: ExtractionRecord | null | undefined,
  updates: ProposedUpdate[] | null | undefined,
): ExtractionRecord {
  const result = cloneExtraction(extraction);
  const raw = result.raw_extraction as Record<string, unknown>;
  const contactProps = nestedBag(raw, "contact_properties");
  const companyProps = nestedBag(raw, "company_properties");

  for (const u of updates || []) {
    if (!u || isInsightsField(u.field_name)) continue;
    const val = u.new_value != null ? String(u.new_value).trim() : "";
    if (!val) continue;
    const objectType = u.object_type || "deals";

    if (objectType === "contacts" && u.field_name !== "contact_name") {
      contactProps[u.field_name as string] = u.field_type === "number" ? parseFloat(val) || null : val;
      continue;
    }
    if (objectType === "companies" && u.field_name !== "company_name") {
      companyProps[u.field_name as string] = u.field_type === "number" ? parseFloat(val) || null : val;
      continue;
    }
    if (objectType === "line_items" || String(u.field_name || "").startsWith("line_item_")) {
      continue;
    }

    if (u.field_name === "contact_name") {
      result.contactName = val;
    } else if (u.field_name === "company_name") {
      result.companyName = val;
      raw.dealname = val;
    } else if (u.field_name === "dealname") {
      result.companyName = val;
      raw.dealname = val;
    } else if (u.field_name === "amount") {
      const amt = parseFloat(val);
      result.dealAmount = Number.isFinite(amt) ? amt : null;
      raw.amount = result.dealAmount;
    } else if (u.field_name === "closedate" || u.field_name === "CloseDate") {
      const iso = parseFlexibleDateToIso(val) || val;
      result.closeDate = iso;
      raw.closedate = iso;
      raw.CloseDate = iso;
    } else if (u.field_name === "dealstage") {
      result.dealStage = val;
      raw.dealstage = val;
    } else if (val) {
      if (u.field_type === "number") {
        raw[u.field_name as string] = parseFloat(val) || null;
      } else if (u.field_type === "date" || u.field_type === "datetime") {
        raw[u.field_name as string] = parseFlexibleDateToIso(val) || val;
      } else {
        raw[u.field_name as string] = val;
      }
    }
  }

  raw.contact_properties = contactProps;
  raw.company_properties = companyProps;
  result.raw_extraction = raw;
  return result;
}

export function stripOmittedFields(
  extraction: ExtractionRecord | null | undefined,
  omittedKeys: Array<string | null | undefined> | null | undefined,
): ExtractionRecord {
  const result = cloneExtraction(extraction);
  const raw = result.raw_extraction as Record<string, unknown>;
  const contactProps = nestedBag(raw, "contact_properties");
  const companyProps = nestedBag(raw, "company_properties");

  for (const key of omittedKeys || []) {
    if (!key) continue;
    const sep = String(key).indexOf(":");
    if (sep < 0) continue;
    const objectType = String(key).slice(0, sep);
    const fieldName = String(key).slice(sep + 1);

    if (objectType === "contacts") {
      delete contactProps[fieldName];
      for (const top of CONTACT_IDENTITY_TOP[fieldName] || []) {
        result[top] = null;
      }
    } else if (objectType === "companies") {
      delete companyProps[fieldName];
      for (const top of COMPANY_IDENTITY_TOP[fieldName] || []) {
        result[top] = null;
      }
    } else if (objectType === "deals") {
      delete raw[fieldName];
      for (const alias of DEAL_RAW_ALIASES[fieldName] || [fieldName]) {
        delete raw[alias];
      }
      for (const top of DEAL_IDENTITY_TOP[fieldName] || []) {
        result[top] = null;
      }
    }
  }

  raw.contact_properties = contactProps;
  raw.company_properties = companyProps;
  result.raw_extraction = raw;
  return result;
}

export function buildApproveExtraction({
  memoExtraction,
  updates,
  omittedKeys,
  summary,
  nextSteps,
}: {
  memoExtraction?: ExtractionRecord | null;
  updates?: ProposedUpdate[] | null;
  omittedKeys?: Array<string | null | undefined> | null;
  summary?: string | null;
  nextSteps?: string[] | null;
} = {}): ExtractionRecord {
  let next = applyProposedUpdates(memoExtraction || {}, updates || []);
  next = stripOmittedFields(next, omittedKeys || []);

  const summaryText = summary != null ? String(summary).trim() : "";
  next.summary = summaryText;
  next.raw_extraction = { ...(next.raw_extraction || {}) };
  next.raw_extraction.description = summaryText;

  const selectedSteps = Array.isArray(nextSteps)
    ? nextSteps.map((s) => String(s || "").trim()).filter(Boolean)
    : [];
  next.nextSteps = selectedSteps;
  if (selectedSteps[0]) next.raw_extraction.hs_next_step = selectedSteps[0];
  else delete next.raw_extraction.hs_next_step;

  return next;
}

export function omittedKeysFrom(
  original: ProposedUpdate[] | null | undefined,
  current: ProposedUpdate[] | null | undefined,
): string[] {
  const currentSet = new Set(
    (current || []).map((u) => proposedFieldKey(u)).filter((k): k is string => Boolean(k)),
  );
  return (original || [])
    .map((u) => proposedFieldKey(u))
    .filter((k): k is string => Boolean(k) && !currentSet.has(k));
}
