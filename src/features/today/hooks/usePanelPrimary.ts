import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { HomeRow } from "@shared/ui/home.js";
import { useHomeColumn } from "@/components/dashboard/HomeColumn";
import { useOptionalDialerFocus } from "@/features/calling/DialerFocusProvider";
import {
  contactPhone,
  exactContact,
  HOME_PANEL_PHONE_KEY,
  panelPrimary,
  type ContactHit,
  type PanelPrimary,
  type PanelRowKind,
} from "@/lib/contact-panel";
import { crmApi } from "@/lib/api/crm";
import { contactRecordUrl } from "@/lib/today";

export function panelRowKind(row: HomeRow): PanelRowKind {
  if (row.kind === "meeting") return "meeting";
  if (row.kind === "confirm") return "confirm";
  if (row.kind === "followup") return "followup";
  if (row.kind === "review") return "review";
  return "call";
}

export function panelCrmHref(
  row: HomeRow,
  provider: string | null,
  portalId: string | null,
): string | null {
  const openUrl =
    row.kind === "call" || row.kind === "meeting" || row.kind === "confirm" ? row.item.open_url : null;
  return openUrl || contactRecordUrl(provider, portalId, row.contactId);
}

export function usePanelPrimary(
  row: HomeRow | null,
  {
    provider,
    portalId,
  }: {
    provider: string | null;
    portalId: string | null;
  },
) {
  const column = useHomeColumn();
  const dialer = useOptionalDialerFocus();
  const queryClient = useQueryClient();
  const canDial = column?.canDial ?? false;
  const contactId = row?.contactId ?? null;
  const kind = row ? panelRowKind(row) : "call";
  const crmHref = row ? panelCrmHref(row, provider, portalId) : null;

  const phoneQuery = useQuery({
    queryKey: [HOME_PANEL_PHONE_KEY, contactId],
    queryFn: () => crmApi.searchContacts(contactId as string),
    enabled: Boolean(contactId && canDial),
    staleTime: 60_000,
  });

  const contact: ContactHit | null = exactContact(phoneQuery.data, contactId);
  const phone = contactPhone(phoneQuery.data, contactId);
  const primary: PanelPrimary = row
    ? panelPrimary({ kind, contactId, canDial, phone, crmHref })
    : null;

  const fetchPhoneFor = useCallback(
    async (id: string) => {
      if (!canDial) return undefined;
      const hits = await queryClient.fetchQuery({
        queryKey: [HOME_PANEL_PHONE_KEY, id],
        queryFn: () => crmApi.searchContacts(id),
        staleTime: 60_000,
      });
      return contactPhone(hits, id);
    },
    [canDial, queryClient],
  );

  const runPrimary = useCallback(
    async (
      actions: {
        confirm: (item: Extract<HomeRow, { kind: "confirm" }>["item"]) => Promise<void>;
        openMemo: (memoId: string) => void;
      },
      forRow: HomeRow | null = row,
    ) => {
      const active = forRow ?? row;
      if (!active) return;
      const activeKind = panelRowKind(active);
      const activeContactId = active.contactId;
      const activeCrm = panelCrmHref(active, provider, portalId);
      let activePhone = activeContactId === contactId ? phone : undefined;
      if (activeContactId && canDial && activePhone === undefined) {
        activePhone = await fetchPhoneFor(activeContactId);
      }
      const activePrimary = panelPrimary({
        kind: activeKind,
        contactId: activeContactId,
        canDial,
        phone: activePhone,
        crmHref: activeCrm,
      });
      if (activePrimary === "confirm" && active.kind === "confirm") {
        await actions.confirm(active.item);
        return;
      }
      if (activePrimary === "call" && activeContactId && canDial && dialer) {
        dialer.openForContact({ contactId: activeContactId, name: active.name ?? null });
        return;
      }
      if (activePrimary === "open" && activeCrm) {
        window.open(activeCrm, "_blank", "noopener,noreferrer");
        return;
      }
      if (active.kind === "review") actions.openMemo(active.entry.memoId);
      else if (active.kind === "followup" && active.entry.action) actions.openMemo(active.entry.memoId);
    },
    [canDial, contactId, dialer, fetchPhoneFor, phone, portalId, provider, row],
  );

  return { primary, phone, contact, crmHref, canDial, kind, runPrimary, phoneQuery };
}
