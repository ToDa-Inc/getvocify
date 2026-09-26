/** Rules of the rep home's contact panel. The panel only paints what these return. */

export type PanelRowKind = "meeting" | "confirm" | "followup" | "review" | "call";
export type PanelPrimary = "confirm" | "call" | "open" | "send" | null;

/**
 * One main action. `phone` is `undefined` while unknown and `null` once the CRM returned the
 * contact without a number: only then does calling give way to opening the CRM.
 */
export function panelPrimary({
  kind,
  contactId,
  canDial,
  canPlace = true,
  phone,
  crmHref,
  followupReady,
  inReview = false,
}: {
  kind: PanelRowKind;
  contactId: string | null;
  canDial: boolean;
  canPlace?: boolean;
  phone: string | null | undefined;
  crmHref: string | null;
  followupReady?: boolean;
  inReview?: boolean;
}): PanelPrimary {
  if (kind === "confirm") return "confirm";
  if (followupReady && (kind === "followup" || inReview)) return "send";
  if (inReview) return null;
  if (contactId && canDial && canPlace && phone !== null) return "call";
  return crmHref ? "open" : null;
}

/**
 * The single filled pill in the panel. «Enviar» is the follow-up card's own pill, so the panel
 * paints no second one; «Revisar y guardar» steps back to a text action when a send is ready.
 */
export function panelFilledPill({
  primary,
  inReview,
  reviewSave,
}: {
  primary: PanelPrimary;
  inReview: boolean;
  reviewSave: boolean;
}): "followup" | "review_save" | "primary" | null {
  if (primary === "send") return "followup";
  if (inReview) return reviewSave ? "review_save" : null;
  return primary && primary !== "confirm" ? "primary" : null;
}

/** A row of the dialer's CRM contact search. */
export type ContactHit = {
  contact_id?: string | null;
  name?: string | null;
  phone?: string | null;
  jobtitle?: string | null;
  company_name?: string | null;
};

export function exactContact(hits: ContactHit[] | undefined, contactId: string | null): ContactHit | null {
  if (!hits || !contactId) return null;
  return hits.find((row) => row.contact_id === contactId) ?? null;
}

/** The phone of that exact contact. Another search result's number is never shown. */
export function contactPhone(hits: ContactHit[] | undefined, contactId: string | null): string | null | undefined {
  const hit = exactContact(hits, contactId);
  if (!hit) return undefined;
  return hit.phone?.trim() || null;
}

/** Only HubSpot memos carry a contact id to filter on. */
export function showsHistory(provider: string | null | undefined): boolean {
  return provider === "hubspot";
}

/** No scope: the rep's own conversations, also for an owner or admin. */
export function historyRequest(contactId: string): string {
  const params = new URLSearchParams({ hubspot_contact_id: contactId, reached_only: "true", limit: "3" });
  return `/memos?${params.toString()}`;
}

const KIND_KEYS: Record<string, "panel_kind_call" | "panel_kind_meeting" | "panel_kind_visit"> = {
  call: "panel_kind_call",
  meeting: "panel_kind_meeting",
  visit: "panel_kind_visit",
};

export type ConversationKindKey = "panel_kind_call" | "panel_kind_meeting" | "panel_kind_visit" | "panel_kind_conversation";

export function conversationLine(
  memo: { createdAt: string; interactionKind?: string | null; audioDuration?: number | null },
  { locale, timeZone }: { locale: string; timeZone?: string },
): { date: string; kindKey: ConversationKindKey; minutes: number | null } {
  const date = new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", timeZone }).format(new Date(memo.createdAt));
  const seconds = Number(memo.audioDuration);
  const minutes = Number.isFinite(seconds) ? Math.round(seconds / 60) : 0;
  return {
    date,
    kindKey: KIND_KEYS[memo.interactionKind ?? ""] ?? "panel_kind_conversation",
    minutes: minutes > 0 ? minutes : null,
  };
}

export function firstName(name: string | null | undefined): string | null {
  return name?.trim().split(/\s+/)[0] || null;
}

export function initials(name: string | null | undefined): string {
  const words = (name ?? "").trim().split(/\s+/).filter(Boolean);
  if (!words.length) return "";
  const first = words[0][0];
  const last = words.length > 1 ? words[words.length - 1][0] : "";
  return `${first}${last}`.toUpperCase();
}

/** Job title and company for the header — never the call quote in `detail`. */
export function panelHeaderSubtitle(
  contact: ContactHit | null,
  companyName: string | null | undefined,
  confirmDetail?: string | null,
): string | null {
  if (confirmDetail != null) return confirmDetail.trim() || null;
  const parts = [contact?.jobtitle?.trim(), companyName?.trim()].filter(Boolean);
  return parts.length ? parts.join(" · ") : null;
}

/** Meeting line above the brief; without a time, only «Hoy · sin hora». */
export function panelMeetingLine(
  time: string | null | undefined,
  copy: { panel_meeting_today: string; home_meeting_no_time: string },
): string {
  if (!time) return copy.home_meeting_no_time;
  return copy.panel_meeting_today.replace("{time}", time);
}

export const HOME_PANEL_PHONE_KEY = "home-panel-phone";
