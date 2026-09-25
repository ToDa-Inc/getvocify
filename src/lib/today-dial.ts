import { dialTargetFromContact } from "./dial-target.ts";
import type { TodayItem } from "./today.ts";

export type TodayDialContact = {
  contact_id: string;
  phone?: string | null;
  name?: string | null;
};

/** Dial the card contact by id — no search box involved. */
export function callTargetFromTodayItem(
  item: Pick<TodayItem, "contact_id">,
  contacts: TodayDialContact[],
): { contactId: string; phone: string; name: string } | null {
  const id = item.contact_id;
  if (!id) return null;
  const hit = contacts.find((row) => row.contact_id === id);
  if (!hit) return null;
  const phone = dialTargetFromContact(hit);
  if (!phone) return null;
  return {
    contactId: String(id),
    phone,
    name: (hit.name || phone).trim(),
  };
}
