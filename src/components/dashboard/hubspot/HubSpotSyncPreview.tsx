import { useState, useEffect, useCallback, useRef, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MENU_TOKENS, THEME_TOKENS } from "@/lib/theme/tokens";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { crmApi } from "@/lib/api/crm";
import { useAuth } from "@/features/auth";
import { memosApi } from "@/features/memos/api";
import { toast } from "sonner";
import {
  Check,
  AlertCircle,
  ChevronDown,
  Pencil,
  Trash2,
  Search,
  X,
  Plus,
  UserCheck,
  Briefcase,
  Building,
} from "lucide-react";
import { ExtractionDatePicker } from "@/components/dashboard/crm/ExtractionDatePicker";
import { formatCrmDateForDisplay, isCrmDateField } from "@/lib/crm-date";
import {
  buildApproveExtraction,
  canEditOrRemoveProposedField,
  omittedKeysFrom,
  proposedFieldKey,
} from "@/lib/extraction-omit";
import { VocifyLoader, VocifySpinner } from "@/components/ui/vocify-loader";
import { isUncertainExtractionConfidence } from "@/shared/lib/constants";
import { CopilotNote } from "@/components/dashboard/CopilotNote";
import {
  clearCachedPreview,
  getCachedPreview,
  previewCacheKey,
  setCachedPreview,
} from "@/lib/preview-cache";
import { AnimIcon } from "@/components/ui/anim-icon";

/** The "—" choice on an option field: Radix items cannot carry "". */
const NO_VALUE = "__none__";

interface HubSpotSyncPreviewProps {
  memoId: string;
  initialDealId?: string | null;
  initialContactId?: string | null;
  fallbackContactName?: string | null;
  /** Bust preview cache when memo transcript/extraction changes */
  previewRefreshKey?: string;
  /** Structured call note from extraction — shown as the copilot summary */
  callSummary?: string | null;
  /** Memo already synced (manual Approve or skip-Approve write). */
  alreadyWritten?: boolean;
  /** Owner/admin viewing a teammate memo — show fields and note, do not sync. */
  readOnly?: boolean;
  reviewAuthorName?: string | null;
  onSuccess: (data: any) => void;
  onContactName?: (name: string | null) => void;
  onContactEmail?: (email: string | null) => void;
  /** Lista 4 T4: Hoy's 400px side panel - tighter spacing, errors inline under the button. */
  compact?: boolean;
  /** Rendered right above the confirm button (the after-call outcome step). */
  beforeConfirm?: ReactNode;
  /** Extra approve fields (the after-call outcome). */
  approveExtra?: Record<string, unknown> | null;
  /** When set, the confirm button is disabled and says why (e.g. "Pick the outcome"). */
  confirmBlockedLabel?: string | null;
  /** Replaces the confirm button's label when nothing blocks it. */
  confirmLabel?: string | null;
  /** Post-call tabs: the panel on show. Unset keeps everything stacked (Hoy's side panel). */
  activeTab?: string | null;
  /** The tab bar, under who/deal: tabs never hide the target or the confirm. */
  tabBar?: ReactNode;
  /** Top of the note panel (the rep's own note and objections: never below the fold). */
  noteLead?: ReactNode;
  /** Bottom of the note panel. */
  noteExtra?: ReactNode;
  /** Top of the tasks panel. */
  tasksLead?: ReactNode;
  /** Panels the page owns (email, coaching). Hidden, never unmounted, so drafts survive. */
  tabPanels?: ReactNode;
  onTabCounts?: (counts: { fields: number; tasks: number }) => void;
  /** Memo review: the panel fills its pane and scrolls inside it (lg+); tabs stay on top, confirm at the bottom. */
  paneled?: boolean;
}

/**
 * Minimum match_confidence (0-1) required to auto-target a deal without prompting.
 */
const CONFIDENT_MATCH_THRESHOLD = 0.7;

function summaryForApprove(
  base: Record<string, unknown>,
  updates: Array<{ field_name?: string; new_value?: unknown }>,
  editedUpdates: unknown[] | null,
): string {
  const desc = updates.find((u) => u.field_name === "description" || u.field_name === "Description");
  const baseSummary = String(
    (base.summary as string) ||
      ((base.raw_extraction as Record<string, unknown> | undefined)?.description as string) ||
      "",
  ).trim();
  const userEditedDescription =
    Array.isArray(editedUpdates) &&
    editedUpdates.some((u: { field_name?: string }) => u?.field_name === "description" || u?.field_name === "Description");
  if (userEditedDescription) return String(desc?.new_value ?? "").trim();
  return baseSummary || String(desc?.new_value ?? "").trim();
}

function nextStepsForApprove(
  base: Record<string, unknown>,
  updates: Array<{ field_name?: string; new_value?: unknown }>,
): string[] {
  const tasks = updates
    .filter((u) => String(u.field_name || "").startsWith("next_step_task_"))
    .sort(
      (a, b) =>
        parseInt(String(a.field_name).replace("next_step_task_", ""), 10) -
        parseInt(String(b.field_name).replace("next_step_task_", ""), 10),
    )
    .map((u) => String(u.new_value ?? "").trim())
    .filter(Boolean);
  if (tasks.length) return tasks;
  const hs = updates.find((u) => u.field_name === "hs_next_step");
  if (hs?.new_value) return [String(hs.new_value).trim()].filter(Boolean);
  return Array.isArray(base.nextSteps) ? (base.nextSteps as string[]) : [];
}

/** For enum/select fields (e.g. Deal Stage), show the human label instead of raw value */
function optionLabelFor(value: unknown, options?: Array<{ value: string; label?: string }>): string {
  const raw = value ?? "—";
  if (options && options.length > 0) {
    const match = options.find((o) => o.value === String(value ?? ""));
    if (match) return match.label ?? match.value;
  }
  return String(raw);
}

export const HubSpotSyncPreview = ({
  memoId,
  onSuccess,
  initialDealId,
  initialContactId,
  fallbackContactName = "",
  previewRefreshKey = "default",
  callSummary = "",
  alreadyWritten = false,
  readOnly = false,
  reviewAuthorName = null,
  onContactName,
  onContactEmail,
  compact = false,
  beforeConfirm = null,
  approveExtra = null,
  confirmBlockedLabel = null,
  confirmLabel = null,
  activeTab = null,
  tabBar = null,
  noteLead = null,
  noteExtra = null,
  tasksLead = null,
  tabPanels = null,
  paneled = false,
  onTabCounts,
}: HubSpotSyncPreviewProps) => {
  const { user } = useAuth();
  const loggedAs = user?.fullName || user?.email;
  const [loading, setLoading] = useState(true);
  const [isSwitchingTarget, setIsSwitchingTarget] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [preview, setPreview] = useState<any>(null);
  const [extractionError, setExtractionError] = useState(false);
  const [retryKey, setRetryKey] = useState(0);
  const [reExtracting, setReExtracting] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);

  // Active target selection tracking
  const [selectedContactId, setSelectedContactId] = useState<string | null>(initialContactId || null);
  const [selectedDealId, setSelectedDealId] = useState<string | null>(initialDealId || null);
  const [isNewDealRequested, setIsNewDealRequested] = useState(false);
  const [isSkipDealRequested, setIsSkipDealRequested] = useState(false);

  // UI pickers open state
  const [contactPickerOpen, setContactPickerOpen] = useState(false);
  const [dealPickerOpen, setDealPickerOpen] = useState(false);

  // Search state
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [contactSearchQuery, setContactSearchQuery] = useState("");
  const [contactSearchResults, setContactSearchResults] = useState<any[]>([]);
  const [isSearchingContacts, setIsSearchingContacts] = useState(false);

  // Field edits
  const [editedUpdates, setEditedUpdates] = useState<any[] | null>(null);
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [showAddField, setShowAddField] = useState<"fields" | "tasks" | null>(null);
  const [omittedKeys, setOmittedKeys] = useState<string[]>([]);

  // Weak matches and manual deal naming
  const [needsDealDecision, setNeedsDealDecision] = useState(false);
  const [dealDecisionMade, setDealDecisionMade] = useState(true);
  const [weakMatches, setWeakMatches] = useState<any[]>([]);
  const [confirmingNewDeal, setConfirmingNewDeal] = useState(false);
  const [manualDealName, setManualDealName] = useState("");

  const searchQueryRef = useRef("");
  const contactSearchQueryRef = useRef("");
  const memoIdRef = useRef(memoId);
  memoIdRef.current = memoId;

  const applyPreviewDecisions = useCallback((previewData: any) => {
    const candidates = Array.isArray(previewData.contact_candidates)
      ? previewData.contact_candidates
      : [];
    const matches = Array.isArray(previewData.matched_deals) ? previewData.matched_deals : [];
    const topMatch = matches[0];
    const isConfident = !!topMatch && (topMatch.match_confidence ?? 0) >= CONFIDENT_MATCH_THRESHOLD;

    setWeakMatches(matches);

    if (candidates.length > 0 && !previewData.selected_contact) {
      setNeedsDealDecision(false);
      setDealDecisionMade(false);
    } else if (previewData.selected_contact || previewData.skip_deal) {
      setNeedsDealDecision(false);
      setDealDecisionMade(true);
    } else {
      if (!isConfident && !previewData.selected_deal && !previewData.is_new_deal) {
        setNeedsDealDecision(true);
        setDealDecisionMade(false);
      } else {
        setNeedsDealDecision(false);
        setDealDecisionMade(true);
      }
    }
  }, []);

  const fetchPreview = useCallback(
    async (
      dealIdArg?: string | null,
      opts?: { createNewDeal?: boolean; contactId?: string | null; skipDeal?: boolean },
    ) => {
      const requestedMemoId = memoId;
      const targetContactId =
        opts?.contactId !== undefined
          ? opts.contactId
          : selectedContactId || preview?.selected_contact?.contact_id || null;

      const isCreatingNew = opts?.createNewDeal ?? (isNewDealRequested && !dealIdArg);
      const isSkippingDeal = opts?.skipDeal ?? (isSkipDealRequested && !dealIdArg && !isCreatingNew);

      const targetDealId =
        dealIdArg !== undefined
          ? dealIdArg
          : isCreatingNew || isSkippingDeal
            ? null
            : selectedDealId || preview?.selected_deal?.deal_id || initialDealId || null;

      const cacheKey = previewCacheKey({
        memoId,
        dealId: targetDealId,
        contactId: targetContactId,
        createNewDeal: isCreatingNew,
        refreshKey: previewRefreshKey,
      });

      if (!preview) {
        setLoading(true);
      } else {
        setIsSwitchingTarget(true);
      }

      try {
        const previewData = await crmApi.getPreview(memoId, targetDealId || undefined, {
          createNewDeal: isCreatingNew,
          contactId: targetContactId || undefined,
        });

        if (memoIdRef.current !== requestedMemoId) return undefined;

        setPreview(previewData);
        setCachedPreview(cacheKey, previewData);

        // Update target tracking
        if (previewData.selected_contact?.contact_id) {
          setSelectedContactId(previewData.selected_contact.contact_id);
        } else if (opts?.contactId === null) {
          setSelectedContactId(null);
        }

        if (previewData.selected_deal?.deal_id) {
          setSelectedDealId(previewData.selected_deal.deal_id);
          setIsNewDealRequested(false);
          setIsSkipDealRequested(false);
        } else if (isCreatingNew) {
          setSelectedDealId(null);
          setIsNewDealRequested(true);
          setIsSkipDealRequested(false);
        } else if (isSkippingDeal) {
          setSelectedDealId(null);
          setIsNewDealRequested(false);
          setIsSkipDealRequested(true);
        }

        applyPreviewDecisions(previewData);
        return previewData;
      } catch (err: any) {
        if (memoIdRef.current !== requestedMemoId) return undefined;
        toast.error("Failed to load update preview");
        return undefined;
      } finally {
        if (memoIdRef.current === requestedMemoId) {
          setLoading(false);
          setIsSwitchingTarget(false);
        }
      }
    },
    [
      memoId,
      initialDealId,
      initialContactId,
      previewRefreshKey,
      selectedContactId,
      selectedDealId,
      isNewDealRequested,
      isSkipDealRequested,
      preview,
      applyPreviewDecisions,
    ],
  );

  // Init reads the latest fetchPreview through a ref: depending on it would re-run init (and
  // snap back to the initial contact) every time the rep picks a contact or deal.
  const fetchPreviewRef = useRef(fetchPreview);
  fetchPreviewRef.current = fetchPreview;

  useEffect(() => {
    let cancelled = false;
    const fetchPreview: typeof fetchPreviewRef.current = (...args) => fetchPreviewRef.current(...args);
    const init = async () => {
      setPreview(null);
      setEditedUpdates(null);
      setOmittedKeys([]);
      setLoading(true);
      setNeedsDealDecision(false);
      setDealDecisionMade(true);
      setWeakMatches([]);
      setConfirmingNewDeal(false);
      setManualDealName("");
      setExtractionError(false);
      setDealPickerOpen(false);
      setContactPickerOpen(false);
      setSearchResults([]);
      setSearchQuery("");
      setContactSearchResults([]);
      setContactSearchQuery("");
      setEditingIdx(null);
      setShowAddField(null);

      const cacheKey = previewCacheKey({
        memoId,
        dealId: initialDealId || null,
        contactId: initialContactId || null,
        refreshKey: previewRefreshKey,
      });
      const cached = getCachedPreview(cacheKey);
      if (cached) {
        setPreview(cached);
        if (cached.selected_contact?.contact_id) {
          setSelectedContactId(cached.selected_contact.contact_id);
        }
        if (cached.selected_deal?.deal_id) {
          setSelectedDealId(cached.selected_deal.deal_id);
        }
        applyPreviewDecisions(cached);
        setLoading(false);
        return;
      }

      try {
        if (initialDealId) {
          await fetchPreview(initialDealId, { contactId: initialContactId || undefined });
          return;
        }
        const previewData = await fetchPreview(undefined, { contactId: initialContactId || undefined });
        if (cancelled || !previewData) return;

        const candidates = Array.isArray(previewData.contact_candidates)
          ? previewData.contact_candidates
          : [];
        if (candidates.length > 0 && !previewData.selected_contact) {
          applyPreviewDecisions(previewData);
        } else if (previewData.selected_contact) {
          applyPreviewDecisions(previewData);
        } else {
          const matches = Array.isArray(previewData.matched_deals) ? previewData.matched_deals : [];
          const topMatch = matches[0];
          const isConfident = !!topMatch && (topMatch.match_confidence ?? 0) >= CONFIDENT_MATCH_THRESHOLD;
          if (isConfident && topMatch.deal_id && !previewData.selected_deal) {
            await fetchPreview(topMatch.deal_id);
          } else {
            applyPreviewDecisions(previewData);
          }
        }
      } catch (error: any) {
        if (cancelled) return;
        const errStr = String(error?.data?.detail ?? "");
        if (error?.status === 400 && errStr.includes("extraction not available")) {
          setExtractionError(true);
          toast.error("Extraction not available. Wait for processing or use Re-extract.");
        } else {
          toast.error("Failed to load preview");
        }
        setPreview(null);
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };
    init();
    return () => {
      cancelled = true;
    };
  }, [memoId, retryKey, initialDealId, initialContactId, previewRefreshKey, applyPreviewDecisions]);

  const handleReExtract = async () => {
    setReExtracting(true);
    try {
      clearCachedPreview(memoId);
      await memosApi.reExtract(memoId);
      toast.success("Re-extraction started. Loading preview...");
      setExtractionError(false);
      setRetryKey((k) => k + 1);
    } catch (err: any) {
      toast.error(err?.data?.detail || err?.message || "Re-extract failed");
    } finally {
      setReExtracting(false);
    }
  };

  searchQueryRef.current = searchQuery;
  contactSearchQueryRef.current = contactSearchQuery;

  const runSearch = useCallback(async (query: string) => {
    if (!query.trim()) return;
    setIsSearching(true);
    try {
      const results = await crmApi.searchCrmDeals(query);
      if (searchQueryRef.current === query) setSearchResults(results);
    } catch (e: any) {
      if (searchQueryRef.current === query) {
        toast.error(e?.message || e?.data?.detail || "Search failed");
      }
    } finally {
      if (searchQueryRef.current === query) setIsSearching(false);
    }
  }, []);

  const runContactSearch = useCallback(async (query: string) => {
    if (!query.trim()) return;
    setIsSearchingContacts(true);
    try {
      const results = await crmApi.searchContacts(query);
      if (contactSearchQueryRef.current === query) setContactSearchResults(results);
    } catch (e: any) {
      if (contactSearchQueryRef.current === query) {
        toast.error(e?.message || e?.data?.detail || "Contact search failed");
      }
    } finally {
      if (contactSearchQueryRef.current === query) setIsSearchingContacts(false);
    }
  }, []);

  const handleSearch = () => {
    const q = searchQuery.trim();
    if (q.length >= 2) runSearch(q);
  };

  useEffect(() => {
    if (!dealPickerOpen) return;
    const q = searchQuery.trim();
    if (q.length < 2) {
      setSearchResults([]);
      return;
    }
    const timer = setTimeout(() => runSearch(q), 300);
    return () => clearTimeout(timer);
  }, [searchQuery, dealPickerOpen, runSearch]);

  useEffect(() => {
    const pickerVisible = contactPickerOpen;
    if (!pickerVisible) return;
    const q = contactSearchQuery.trim();
    if (q.length < 2) {
      setContactSearchResults([]);
      return;
    }
    const timer = setTimeout(() => runContactSearch(q), 300);
    return () => clearTimeout(timer);
  }, [contactSearchQuery, contactPickerOpen, preview?.selected_contact, runContactSearch]);

  const selectDeal = async (dealId: string) => {
    setSelectedDealId(dealId);
    setIsNewDealRequested(false);
    setIsSkipDealRequested(false);
    setDealPickerOpen(false);
    setSearchResults([]);
    setSearchQuery("");
    setNeedsDealDecision(false);
    setDealDecisionMade(true);
    setConfirmingNewDeal(false);
    await fetchPreview(dealId, {
      contactId: selectedContactId,
      createNewDeal: false,
      skipDeal: false,
    });
  };

  const selectContact = async (contact: { contact_id: string }) => {
    const contactId = contact.contact_id;
    const before = preview;
    const beforeId = selectedContactId;
    setSelectedContactId(contactId);
    setContactPickerOpen(false);
    setContactSearchQuery("");
    setContactSearchResults([]);
    // Show the pick now; the refreshed preview replaces it when it lands.
    setPreview((prev: any) => (prev ? { ...prev, selected_contact: contact } : prev));
    const data = await fetchPreview(selectedDealId, { contactId });
    if (!data && memoIdRef.current === memoId) {
      setPreview(before);
      setSelectedContactId(beforeId);
    }
    if (data?.selected_contact) {
      setNeedsDealDecision(false);
      setDealDecisionMade(true);
    }
  };

  const handleCreateNewDeal = async () => {
    setDealPickerOpen(false);
    setSearchResults([]);
    setSearchQuery("");
    setIsNewDealRequested(true);
    setIsSkipDealRequested(false);
    setSelectedDealId(null);

    const data = await fetchPreview(null, {
      createNewDeal: true,
      contactId: selectedContactId,
    });

    const candidateUpdates = data?.proposed_updates ?? [];
    const hasNameSignal =
      !!data?.new_company ||
      !!data?.new_contact ||
      !!data?.selected_contact ||
      candidateUpdates.some((u: any) => u.field_name === "company_name" || u.field_name === "contact_name");

    if (hasNameSignal) {
      setNeedsDealDecision(false);
      setDealDecisionMade(true);
      setConfirmingNewDeal(false);
    } else {
      setNeedsDealDecision(true);
      setDealDecisionMade(false);
      setConfirmingNewDeal(true);
    }
  };

  const handleSkipDeal = async () => {
    setDealPickerOpen(false);
    setSearchResults([]);
    setSearchQuery("");
    setIsSkipDealRequested(true);
    setIsNewDealRequested(false);
    setSelectedDealId(null);
    setNeedsDealDecision(false);
    setDealDecisionMade(true);
    setConfirmingNewDeal(false);

    await fetchPreview(null, {
      skipDeal: true,
      createNewDeal: false,
      contactId: selectedContactId,
    });
  };

  const confirmManualDealName = () => {
    const name = manualDealName.trim();
    if (!name) return;
    const list = (editedUpdates ?? updates.map((u: any) => ({ ...u }))).filter(
      (u: any) => u.field_name !== "company_name" && u.field_name !== "dealname",
    );
    setEditedUpdates([
      {
        field_name: "dealname",
        field_label: "Deal Name",
        field_type: "string",
        object_type: "deals",
        current_value: null,
        new_value: name,
      },
      ...list,
    ]);
    setNeedsDealDecision(false);
    setDealDecisionMade(true);
    setConfirmingNewDeal(false);
  };

  const selectedContact = preview?.selected_contact ?? null;
  useEffect(() => {
    onContactName?.(selectedContact?.name || null);
  }, [selectedContact?.name, onContactName]);
  useEffect(() => {
    onContactEmail?.(selectedContact?.email || null);
  }, [selectedContact?.email, onContactEmail]);

  const contactCandidates = Array.isArray(preview?.contact_candidates) ? preview.contact_candidates : [];
  const fallbackName = String(fallbackContactName || "").trim();
  const displayContactName = selectedContact?.name || selectedContact?.email || fallbackName;
  const showContactPicker = !readOnly && (contactPickerOpen || !displayContactName);
  const needsContactDecision = !selectedContact && contactCandidates.length > 0 && !displayContactName;
  const skipDeal = !!preview?.skip_deal || isSkipDealRequested;
  const dealMatch = preview?.selected_deal;
  const isNewDeal = (preview?.is_new_deal ?? false) || isNewDealRequested;
  const currentDealId = preview?.selected_deal?.deal_id ?? selectedDealId;

  const updates = editedUpdates ?? preview?.proposed_updates ?? [];
  const availableFields = preview?.available_fields ?? [];
  const OBJECT_ORDER = ["deals", "contacts", "companies", "line_items", "task"];
  const sortedUpdateEntries = [...updates.map((u: any, idx: number) => ({ u, idx }))]
    .filter(({ u }) => u?.field_name && u.field_name !== "description")
    .sort((a, b) => {
      const ao = OBJECT_ORDER.indexOf(a.u?.object_type || "deals");
      const bo = OBJECT_ORDER.indexOf(b.u?.object_type || "deals");
      return (ao < 0 ? 99 : ao) - (bo < 0 ? 99 : bo);
    });
  const tabbed = activeTab != null;
  const isTaskEntry = ({ u }: { u: any }) =>
    (u?.object_type || "deals") === "task" || String(u?.field_name || "").startsWith("next_step_task_");
  const fieldEntries = tabbed ? sortedUpdateEntries.filter((entry) => !isTaskEntry(entry)) : sortedUpdateEntries;
  const taskEntries = tabbed ? sortedUpdateEntries.filter(isTaskEntry) : [];
  useEffect(() => {
    onTabCounts?.({ fields: fieldEntries.length, tasks: taskEntries.length });
  }, [onTabCounts, fieldEntries.length, taskEntries.length]);

  const buildExtractionForSync = async (): Promise<Record<string, unknown> | undefined> => {
    const memo = await memosApi.get(memoId);
    const base = memo?.extraction && typeof memo.extraction === "object" ? { ...memo.extraction } : {};
    const originalUpdates = preview?.proposed_updates ?? [];
    const effectiveUpdates = editedUpdates ?? originalUpdates;
    if (effectiveUpdates.length === 0 && omittedKeys.length === 0) return undefined;
    const omitted = [...omittedKeys, ...omittedKeysFrom(originalUpdates, effectiveUpdates)];
    return buildApproveExtraction({
      memoExtraction: base as Record<string, unknown>,
      updates: effectiveUpdates,
      omittedKeys: omitted,
      summary: summaryForApprove(base as Record<string, unknown>, effectiveUpdates, editedUpdates),
      nextSteps: nextStepsForApprove(base as Record<string, unknown>, effectiveUpdates),
    });
  };

  const handleSync = async () => {
    if (readOnly || confirmBlockedLabel) return;
    setSyncing(true);
    setSyncError(null);
    try {
      const extraction = await buildExtractionForSync();
      const contactId = selectedContact?.contact_id || preview?.selected_contact?.contact_id;
      const companyId = selectedContact?.company_id || preview?.selected_contact?.company_id;
      const effectiveSkipDeal = skipDeal && !isNewDeal && !currentDealId;
      const result = await crmApi.approveSync(
        memoId,
        currentDealId ?? undefined,
        isNewDeal && !effectiveSkipDeal,
        extraction,
        {
          contactId,
          companyId,
          skipDeal: effectiveSkipDeal,
          createCompany: Boolean(preview?.new_company && !companyId),
          extra: approveExtra,
        },
      );
      toast.success(effectiveSkipDeal ? "Contact updated successfully!" : "CRM updated successfully!");
      onSuccess(result);
    } catch (err: any) {
      const detail = err?.data?.detail;
      const message = (typeof detail === "string" ? detail : null) || err?.message || "Failed to sync with CRM";
      if (compact) setSyncError(message);
      toast.error(message);
    } finally {
      setSyncing(false);
    }
  };

  const updateField = (idx: number, newValue: string | number, exitEdit = true) => {
    const list = editedUpdates ?? updates.map((u) => ({ ...u }));
    if (list[idx]) {
      const next = [...list];
      next[idx] = { ...next[idx], new_value: newValue };
      setEditedUpdates(next);
    }
    if (exitEdit) setEditingIdx(null);
  };

  const removeField = (idx: number) => {
    const list = editedUpdates ?? updates.map((u: any) => ({ ...u }));
    const key = proposedFieldKey(list[idx]);
    if (key) setOmittedKeys((prev) => (prev.includes(key) ? prev : [...prev, key]));
    const next = list.slice();
    next[idx] = null;
    setEditedUpdates(next.filter(Boolean));
  };

  const addField = (field: {
    name: string;
    label: string;
    type?: string;
    options?: unknown[];
    object_type?: string;
  }) => {
    const objectType = field.object_type || "deals";
    const key = proposedFieldKey({ field_name: field.name, object_type: objectType });
    if (key) setOmittedKeys((prev) => prev.filter((k) => k !== key));
    const newUpdate = {
      field_name: field.name,
      field_label: field.label,
      field_type: field.type || "string",
      current_value: null,
      new_value: "",
      options: field.options,
      object_type: objectType,
    };
    const list = editedUpdates ?? updates.map((u) => ({ ...u }));
    setEditedUpdates([...list, newUpdate]);
    setShowAddField(null);
    setEditingIdx(list.length);
  };

  // Paneled review: a new tab starts at its top, not wherever the last one was scrolled to.
  const paneBodyRef = useRef<HTMLDivElement | null>(null);
  const tabTopRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const body = paneBodyRef.current;
    const top = tabTopRef.current?.offsetTop;
    if (!paneled || !body || top == null) return;
    if (body.scrollTop > top) body.scrollTop = top;
  }, [activeTab, paneled]);

  if (extractionError) {
    return (
      <div className="flex flex-col items-center justify-center py-20 space-y-6">
        <div className="w-16 h-16 rounded-2xl bg-destructive/10 flex items-center justify-center">
          <AlertCircle className="h-8 w-8 text-destructive" />
        </div>
        <div className="text-center space-y-2 max-w-sm">
          <p className="text-sm font-medium text-foreground">Extraction Not Available</p>
          <p className="text-xs text-muted-foreground">
            Processing may have failed or is still in progress. If you have a transcript, try Re-extract to run the AI
            extraction again.
          </p>
          {!readOnly ? (
          <Button
            onClick={handleReExtract}
            disabled={reExtracting}
            variant="outline"
            className="mt-6 rounded-full border-beige/40 hover:bg-beige/10"
          >
            <AnimIcon name="refresh" state={reExtracting && "busy"} className="mr-2" />
            {reExtracting ? "Re-extracting..." : "Re-extract"}
          </Button>
          ) : null}
        </div>
      </div>
    );
  }

  if (loading && !preview) {
    return (
      <div className="flex flex-col items-center justify-center py-20 space-y-6">
        <VocifyLoader size="lg" label="Analyzing conversation and CRM..." />
        <p className="text-xs text-muted-foreground max-w-xs mx-auto text-center">
          Matching contact, deal, and extracting key CRM properties.
        </p>
      </div>
    );
  }

  const renderUpdateRows = (entries: Array<{ u: any; idx: number }>, showHeaders = true) =>
    entries.map(({ u: update, idx }) => {
      const alreadyApplied = !!update.already_applied;
      const hasCurrent =
        update.current_value != null &&
        String(update.current_value).trim() !== "" &&
        String(update.current_value).trim() !== "(empty)";
      const unchanged =
        hasCurrent &&
        !alreadyApplied &&
        String(update.current_value).trim() === String(update.new_value ?? "").trim();
      const hadExisting = hasCurrent && !unchanged;
      const isOverride = !!hadExisting && !alreadyApplied;
      // Extracted with middling confidence: the rep should check it before it is written.
      const isUncertain = !alreadyApplied && isUncertainExtractionConfidence(update.extraction_confidence);
      const canEditRow = canEditOrRemoveProposedField(update);
      const isEditing = editingIdx === idx;
      const options: Array<{ value: string; label?: string }> = (update.options ?? []).filter(
        (o: { value: unknown }) => o.value != null && String(o.value) !== "",
      );
      // An option field is edited in place, like the extension: the value is the dropdown.
      const inlineSelect = options.length > 0 && !isCrmDateField(update) && canEditRow && !readOnly;
      const selectValue = update.new_value == null || String(update.new_value) === "" ? NO_VALUE : String(update.new_value);
      const valueOutsideOptions = selectValue !== NO_VALUE && !options.some((o) => String(o.value) === selectValue);
      const entryPos = entries.findIndex((e) => e.idx === idx);
      const prevObject = entryPos > 0 ? entries[entryPos - 1].u?.object_type || "deals" : null;
      const currentObject = update.object_type || "deals";
      const showSection = showHeaders && (entryPos === 0 || prevObject !== currentObject);
      const sectionLabel =
        {
          deals: "Deal Properties",
          contacts: "Contact Properties",
          companies: preview?.new_company && !selectedContact?.company_id
            ? "New Company"
            : "Company Properties",
          line_items: "Line Items",
          task: "Tasks",
        }[String(currentObject)] || currentObject;

      return (
        <div key={`${currentObject}-${update.field_name}-${idx}`} className="space-y-2">
          {showSection && (
            <div className="flex items-center gap-2 px-1 pt-2">
              <span className="text-[11px] font-medium tracking-wider uppercase text-beige">
                {sectionLabel}
              </span>
              <span className="h-px flex-1 bg-border/40" />
            </div>
          )}
          <div
            className={`group relative rounded-xl px-3.5 py-3 transition-all flex items-start justify-between gap-3 border ${
              isUncertain
                ? "bg-warning/[0.04] border-warning/30 hover:border-warning/45"
                : isOverride
                ? "bg-destructive/[0.03] border-destructive/25 hover:border-destructive/40"
                : "bg-card border-border/50 hover:border-beige/40 shadow-xs"
            }`}
          >
            <div className="flex-1 min-w-0 space-y-0.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11.5px] font-medium text-muted-foreground">{update.field_label}</span>
                {alreadyApplied ? (
                  <span className="bg-muted text-muted-foreground text-[10px] font-medium px-2 py-0.5 rounded-full shrink-0">
                    Written
                  </span>
                ) : isUncertain ? (
                  <span className="bg-warning/10 text-warning text-[10px] font-medium px-2 py-0.5 rounded-full shrink-0">
                    Not sure
                  </span>
                ) : isOverride ? (
                  <span className="bg-destructive/10 text-destructive text-[10px] font-medium px-2 py-0.5 rounded-full shrink-0">
                    Override
                  </span>
                ) : unchanged ? null : (
                  <span className="bg-success/10 text-success text-[10px] font-medium px-2 py-0.5 rounded-full shrink-0">
                    New
                  </span>
                )}
              </div>

              {hadExisting && (
                <p className="text-[10px] text-destructive line-through">
                  {optionLabelFor(update.current_value, update.options) || "—"}
                </p>
              )}

              {inlineSelect ? (
                <Select
                  value={selectValue}
                  defaultOpen={isEditing}
                  onValueChange={(v) => updateField(idx, v === NO_VALUE ? "" : v)}
                  onOpenChange={(open) => {
                    if (!open && isEditing) setEditingIdx(null);
                  }}
                >
                  <SelectTrigger size="sm" aria-label={update.field_label} className={`mt-1 ${isUncertain ? "text-warning" : "text-success"}`}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NO_VALUE}>—</SelectItem>
                    {valueOutsideOptions ? (
                      <SelectItem value={selectValue}>{selectValue}</SelectItem>
                    ) : null}
                    {options.map((o) => (
                      <SelectItem key={String(o.value)} value={String(o.value)}>
                        {o.label ?? String(o.value)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : isEditing ? (
                <div className="pt-1">
                  {isCrmDateField(update) ? (
                    <ExtractionDatePicker
                      value={String(update.new_value ?? "")}
                      onChange={(iso) => updateField(idx, iso, false)}
                      onClose={() => setEditingIdx(null)}
                    />
                  ) : (
                    <Input
                      autoFocus
                      type={update.field_type === "number" ? "number" : "text"}
                      value={String(update.new_value ?? "")}
                      onChange={(e) => updateField(idx, e.target.value, false)}
                      onBlur={() => setEditingIdx(null)}
                      onKeyDown={(e) => e.key === "Enter" && setEditingIdx(null)}
                      className="h-8 rounded-lg text-xs md:text-xs"
                    />
                  )}
                </div>
              ) : (
                <p
                  className={`text-[13px] font-normal leading-relaxed ${isUncertain ? "text-warning" : "text-success"}`}
                >
                  {isCrmDateField(update)
                    ? formatCrmDateForDisplay(String(update.new_value ?? "")) || update.new_value || "—"
                    : optionLabelFor(update.new_value, update.options)}
                </p>
              )}
            </div>

            {canEditRow && !isEditing && !readOnly && (
              <div className="flex items-center gap-0.5 shrink-0 opacity-60 group-hover:opacity-100 transition-opacity">
                {inlineSelect ? null : (
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Edit ${update.field_label}`}
                  className="h-6 w-6 rounded-full text-muted-foreground hover:text-beige"
                  onClick={() => setEditingIdx(idx)}
                >
                  <Pencil className="h-3 w-3" />
                </Button>
                )}
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Remove ${update.field_label}`}
                  className="h-6 w-6 rounded-full text-muted-foreground hover:text-destructive"
                  onClick={() => removeField(idx)}
                >
                  <Trash2 className="h-3 w-3" />
                </Button>
              </div>
            )}
          </div>
        </div>
      );
    });

  const renderFieldRail = (scope: "fields" | "tasks", heading: string | null) => {
    const addable = availableFields.filter((f: { object_type?: string }) =>
      !tabbed ? true : scope === "tasks" ? f.object_type === "task" : f.object_type !== "task",
    );
    if (!heading && (addable.length === 0 || loading || readOnly) && !isSwitchingTarget) return null;
    return (
      <div className="relative flex items-center justify-between px-1">
        <div className="flex items-center gap-2">
          {heading ? <h5 className={THEME_TOKENS.typography.sectionRail}>{heading}</h5> : null}
          {isSwitchingTarget && <VocifySpinner size={13} className="text-beige" />}
        </div>
        {addable.length > 0 && !loading && !readOnly && (
          <DropdownMenu open={showAddField === scope} onOpenChange={(open) => setShowAddField(open ? scope : null)}>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="text-xs font-normal text-beige hover:bg-beige/10 h-7 px-2.5 rounded-full"
              >
                <Plus className="h-3 w-3 mr-1" />
                {scope === "tasks" ? "Add task" : "Add field"}
              </Button>
            </DropdownMenuTrigger>
            {/* The new row opens its own value picker; keep focus there instead of on this trigger. */}
            <DropdownMenuContent align="end" className="max-h-64 w-64 overflow-y-auto" onCloseAutoFocus={(e) => e.preventDefault()}>
              {(() => {
                const unused = addable.filter((f: { name: string; object_type?: string }) => {
                  const ot = f.object_type || "deals";
                  return !updates.some((u: any) => u?.field_name === f.name && (u?.object_type || "deals") === ot);
                });
                const OBJECT_LABELS: Record<string, string> = {
                  deals: "Deal",
                  contacts: "Contact",
                  companies: "Company",
                };
                if (unused.length === 0) {
                  return <p className={MENU_TOKENS.label}>All available fields added</p>;
                }
                return unused.map(
                  (f: { name: string; label: string; type?: string; options?: unknown[]; object_type?: string }) => (
                    <DropdownMenuItem key={`${f.object_type || "deals"}:${f.name}`} onSelect={() => addField(f)}>
                      <span className="truncate">{f.label || f.name}</span>
                      <span className="ml-auto shrink-0 pl-2 text-xs text-muted-foreground">
                        {OBJECT_LABELS[f.object_type || "deals"] || f.object_type}
                      </span>
                    </DropdownMenuItem>
                  ),
                );
              })()}
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
    );
  };

  const syncFooter = (
      <div className={`border-t border-border/40 ${paneled ? "pt-3" : "pt-4"}`}>
        {readOnly ? (
          <p className={THEME_TOKENS.typography.body}>
            This call belongs to {reviewAuthorName || "a teammate"}. You can read the note and fields; only they can sync it.
          </p>
        ) : (
          <>
        <Button
          variant="hero"
          onClick={handleSync}
          disabled={
            syncing || loading || needsContactDecision || (needsDealDecision && !dealDecisionMade) || Boolean(confirmBlockedLabel)
          }
          className={`w-full bg-beige text-cream hover:bg-beige/90 rounded-full font-medium ${paneled ? "h-10 text-[13px] shadow-sm" : "h-12 text-sm shadow-md"} transition-all`}
        >
          {syncing ? <VocifySpinner size={16} className="mr-2" /> : <Check className="h-4 w-4 mr-2" />}
          {syncing
            ? "Syncing to CRM..."
            : needsContactDecision
              ? "Select a contact first"
              : needsDealDecision && !dealDecisionMade
                ? "Select a deal first"
                : confirmBlockedLabel
                  ? confirmBlockedLabel
                  : confirmLabel
                    ? confirmLabel
                : alreadyWritten
                  ? "Write correction"
                  : skipDeal && selectedContact
                    ? "Confirm & Update Contact"
                    : dealMatch
                      ? "Confirm & Update Deal"
                      : "Confirm & Create Deal"}
        </Button>
        {syncError ? (
          <p role="alert" className="mt-3 text-center text-[12px] text-destructive">{syncError}</p>
        ) : null}
        {alreadyWritten ? (
          <p className="text-[10px] text-muted-foreground text-center mt-2">
            This was written after processing. Edit anything that is wrong and write the correction.
            Lead status is never auto-changed.
          </p>
        ) : loggedAs ? (
          <p className="text-[10px] text-muted-foreground text-center mt-2">
            Calls, notes, and tasks log in HubSpot as {loggedAs}. Existing contact owners stay put.
          </p>
        ) : null}
          </>
        )}
      </div>
  );

  return (
    <div className={paneled ? "review-pane lg:flex lg:h-full lg:flex-col" : undefined}>
    <div
      ref={paneBodyRef}
      className={
        paneled
          ? "relative overflow-x-hidden scrollbar-thin lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:overscroll-contain"
          : undefined
      }
    >
    <div className={`${compact || paneled ? "space-y-5" : "space-y-8"} animate-in fade-in duration-300 ${paneled ? "px-6 pb-6 pt-5" : ""}`}>
      <div className="space-y-2">
      {/* 1. CONTACT TARGET SECTION */}
      <div className="space-y-2">
        {/* Contact Candidates Picker */}
        {showContactPicker && (
          <div className="bg-secondary/5 rounded-2xl p-4 border border-beige/25 space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium text-foreground">
                {contactCandidates.length > 1
                  ? "Several contacts matched — select who to update, or search:"
                  : "Pick who to update, or search another contact:"}
              </p>
              {displayContactName && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 rounded-full"
                  onClick={() => {
                    setContactPickerOpen(false);
                    setContactSearchQuery("");
                    setContactSearchResults([]);
                  }}
                >
                  <X className="h-3.5 w-3.5" />
                </Button>
              )}
            </div>

            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/40" />
                <Input
                  placeholder="Search contacts by name, email, or phone..."
                  value={contactSearchQuery}
                  onChange={(e) => setContactSearchQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && contactSearchQuery.trim().length >= 2) {
                      runContactSearch(contactSearchQuery.trim());
                    }
                  }}
                  className="bg-card border-border/50 rounded-xl pl-10 pr-4 h-8 text-[13px] md:text-[13px]"
                />
              </div>
              <Button
                size="sm"
                onClick={() => {
                  if (contactSearchQuery.trim().length >= 2) runContactSearch(contactSearchQuery.trim());
                }}
                disabled={isSearchingContacts}
                className="bg-beige text-cream hover:bg-beige/90 rounded-full px-3.5 h-8 text-[13px] font-normal shrink-0"
              >
                {isSearchingContacts ? <VocifySpinner size={12} /> : "Search"}
              </Button>
            </div>

            <div className="grid gap-2 max-h-60 overflow-y-auto pr-1 scrollbar-thin">
              {[...contactSearchResults, ...contactCandidates]
                .filter((c: any, idx: number, all: any[]) => {
                  const id = c?.contact_id;
                  return id && all.findIndex((other) => other?.contact_id === id) === idx;
                })
                .map((c: any) => {
                const isSelected = selectedContact?.contact_id === c.contact_id;
                return (
                  <button
                    key={c.contact_id}
                    type="button"
                    onClick={() => selectContact(c)}
                    className={`w-full text-left p-4 rounded-xl border transition-all ${
                      isSelected
                        ? "bg-beige/15 border-beige text-foreground shadow-sm"
                        : "bg-card hover:bg-beige/10 border-border/50 hover:border-beige/40"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-[13px] font-medium text-foreground truncate">{c.name || "Contact"}</p>
                        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground mt-0.5">
                          {c.email && <span>{c.email}</span>}
                          {c.phone && <span>· {c.phone}</span>}
                          {c.company_name && (
                            <span className="inline-flex items-center gap-1 font-medium text-foreground/70">
                              <Building className="h-3 w-3" />
                              {c.company_name}
                            </span>
                          )}
                        </div>
                        {c.match_reason && (
                          <p className="text-[10px] text-muted-foreground/60 italic mt-1.5">{c.match_reason}</p>
                        )}
                      </div>
                      {isSelected ? (
                        <span className="shrink-0 flex items-center justify-center w-6 h-6 rounded-full bg-beige text-cream">
                          <Check className="h-3.5 w-3.5" />
                        </span>
                      ) : null}
                    </div>
                  </button>
                );
              })}
              {contactCandidates.length === 0 && contactSearchResults.length === 0 && (
                <p className="text-xs text-muted-foreground px-1 py-2">
                  {contactSearchQuery.trim().length >= 2
                    ? isSearchingContacts
                      ? "Searching…"
                      : "No contacts found."
                    : "Search by name, email, or phone to pick a contact."}
                </p>
              )}
            </div>
          </div>
        )}

        {/* Selected contact: one row, Change on the right. */}
        {displayContactName && !contactPickerOpen && (
          <div className="flex items-center gap-3 rounded-xl border border-border/50 bg-secondary/5 px-3 py-2">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-success/10 text-success" title="Contact">
              <UserCheck className="h-3.5 w-3.5" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] text-foreground">
                <span className="font-medium">{selectedContact?.name || displayContactName}</span>
                {[selectedContact?.company_name, selectedContact?.email, selectedContact?.phone].filter(Boolean).length ? (
                  <span className="text-muted-foreground">
                    {"  "}
                    {[selectedContact?.company_name, selectedContact?.email, selectedContact?.phone].filter(Boolean).join(" · ")}
                  </span>
                ) : null}
              </p>
              {preview?.new_company && !selectedContact?.company_id ? (
                <p className="truncate text-[11.5px] text-beige">
                  {preview.new_company.name
                    ? `No company yet. Confirm creates ${preview.new_company.name}.`
                    : "No company on this contact yet."}
                </p>
              ) : null}
            </div>
            {!readOnly ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setContactPickerOpen(true)}
                className="h-7 shrink-0 rounded-full px-2.5 text-xs font-normal text-beige hover:bg-beige/10"
              >
                Change
              </Button>
            ) : null}
          </div>
        )}
      </div>

      {/* 2. DEAL TARGET SECTION */}
      <div className="space-y-2">
        {/* Deal Picker Drawer (Search + Matched Deals + Create New + Contact Only) */}
        {!readOnly && (dealPickerOpen || (needsDealDecision && !dealDecisionMade)) && (
          <div className="bg-secondary/5 rounded-2xl p-4 border border-beige/30 space-y-4">
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs font-medium text-foreground">
                {needsDealDecision && !dealDecisionMade
                  ? "Confirm where this call should land:"
                  : "Select or search deal target:"}
              </p>
              {dealDecisionMade && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 rounded-full shrink-0"
                  onClick={() => setDealPickerOpen(false)}
                >
                  <X className="h-3.5 w-3.5" />
                </Button>
              )}
            </div>

            {/* Deal Search Box */}
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/40" />
                <Input
                  placeholder="Search deals by name..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                  className="bg-card border-border/50 rounded-xl pl-10 pr-4 h-8 text-[13px] md:text-[13px]"
                />
              </div>
              <Button
                size="sm"
                onClick={handleSearch}
                disabled={isSearching}
                className="bg-beige text-cream hover:bg-beige/90 rounded-full px-3.5 h-8 text-[13px] font-normal shrink-0"
              >
                {isSearching ? <VocifySpinner size={12} /> : "Search"}
              </Button>
            </div>

            {/* Search Results */}
            {searchResults.length > 0 && (
              <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1 scrollbar-thin">
                <p className="text-[11px] font-medium text-muted-foreground px-1">Search results</p>
                {searchResults.map((d: any) => (
                  <button
                    key={d.deal_id}
                    type="button"
                    onClick={() => selectDeal(d.deal_id)}
                    className="w-full text-left p-3 rounded-xl bg-card border border-border/40 hover:border-beige hover:bg-beige/5 transition-all flex items-center justify-between"
                  >
                    <div className="min-w-0">
                      <p className="text-[13px] font-medium text-foreground truncate">{d.deal_name}</p>
                      <p className="text-xs text-muted-foreground">
                        {d.stage?.replace(/_/g, " ")} {d.amount ? `· ${d.amount}` : ""}
                      </p>
                    </div>
                    <ChevronDown className="h-4 w-4 -rotate-90 text-muted-foreground/50 shrink-0" />
                  </button>
                ))}
              </div>
            )}

            {/* Matched Deals List */}
            {weakMatches.length > 0 && searchResults.length === 0 && (
              <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1 scrollbar-thin">
                <p className="text-[11px] font-medium text-muted-foreground px-1">Suggested deals</p>
                {weakMatches.map((m: any) => {
                  const isSelected = selectedDealId === m.deal_id;
                  return (
                    <button
                      key={m.deal_id}
                      type="button"
                      onClick={() => selectDeal(m.deal_id)}
                      className={`w-full text-left p-3 rounded-xl border transition-all flex items-center justify-between ${
                        isSelected
                          ? "bg-beige/15 border-beige text-foreground shadow-sm"
                          : "bg-card hover:bg-beige/10 border-border/40 hover:border-beige/40"
                      }`}
                    >
                      <div className="min-w-0">
                        <p className="text-[13px] font-medium text-foreground truncate">{m.deal_name}</p>
                        <p className="text-[11px] text-muted-foreground/60 italic">{m.match_reason}</p>
                      </div>
                      <ChevronDown className="h-4 w-4 -rotate-90 text-muted-foreground/50 shrink-0" />
                    </button>
                  );
                })}
              </div>
            )}

            {/* Manual Deal Name input when required */}
            {confirmingNewDeal && (
              <div className="space-y-2 pt-2 border-t border-border/20">
                <p className="text-xs text-muted-foreground">Enter a name for the new deal:</p>
                <div className="flex items-center gap-2">
                  <Input
                    autoFocus
                    placeholder="e.g. Acme Corp - Software Contract"
                    value={manualDealName}
                    onChange={(e) => setManualDealName(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && confirmManualDealName()}
                    className="bg-card border-border/50 rounded-xl px-3 h-8 text-[13px] md:text-[13px] flex-1"
                  />
                  <Button
                    size="sm"
                    onClick={confirmManualDealName}
                    disabled={!manualDealName.trim()}
                    className="bg-beige text-cream hover:bg-beige/90 rounded-full px-3.5 h-8 text-[13px] font-normal shrink-0"
                  >
                    Confirm Name
                  </Button>
                </div>
              </div>
            )}

            {/* Quick Actions in Picker */}
            <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-border/20">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleCreateNewDeal}
                className="rounded-xl text-xs font-normal border-beige/40 hover:bg-beige/10"
              >
                <Plus className="h-3 w-3 mr-1" />
                Create a new deal
              </Button>
              {selectedContact && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={handleSkipDeal}
                  className="rounded-xl text-xs font-normal text-muted-foreground hover:text-foreground"
                >
                  Contact only (skip deal)
                </Button>
              )}
            </div>
          </div>
        )}

        {/* Selected deal: one row, Change on the right. */}
        {!dealPickerOpen && !(needsDealDecision && !dealDecisionMade) && (
          <div className="flex items-center gap-3 rounded-xl border border-border/50 bg-secondary/5 px-3 py-2">
            <span
              title="Deal"
              className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${
                dealMatch ? "bg-success/10 text-success" : skipDeal ? "bg-foreground/[0.05] text-muted-foreground" : "bg-beige/15 text-beige"
              }`}
            >
              <Briefcase className="h-3.5 w-3.5" />
            </span>
            <p className="min-w-0 flex-1 truncate text-[13px] text-foreground">
              <span className="font-medium">
                {dealMatch ? dealMatch.deal_name || "Existing deal" : skipDeal ? "No deal" : "New deal"}
              </span>
              <span className="text-muted-foreground">
                {"  "}
                {dealMatch
                  ? "Updates this deal"
                  : skipDeal
                    ? `Only ${selectedContact?.name || "the contact"} is updated`
                    : "Created in your main pipeline"}
              </span>
            </p>
            {!readOnly ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setDealPickerOpen(true)}
                className="h-7 shrink-0 rounded-full px-2.5 text-xs font-normal text-beige hover:bg-beige/10"
              >
                Change
              </Button>
            ) : null}
          </div>
        )}
      </div>
      </div>

      {paneled && tabBar ? (
        <>
          <div ref={tabTopRef} aria-hidden />
          {/* Stays on top while a long panel scrolls: the rep never hunts for the tabs. */}
          <div className="sticky top-0 z-10 -mx-6 bg-card px-6">{tabBar}</div>
        </>
      ) : (
        tabBar
      )}

      {/* 3. CALL NOTE / COPILOT SUMMARY */}
      <div
        id={tabbed ? "review-panel-note" : undefined}
        role={tabbed ? "tabpanel" : undefined}
        aria-labelledby={tabbed ? "review-tab-note" : undefined}
        hidden={tabbed && activeTab !== "note"}
        className={tabbed ? "space-y-4" : undefined}
      >
        {tabbed ? noteLead : null}
        {callSummary ? (
          <div className={tabbed ? "" : "space-y-3 pt-2"}>
            {tabbed ? null : <h5 className={THEME_TOKENS.typography.sectionRail}>Call note</h5>}
            <div className="px-4 py-3.5 rounded-2xl bg-secondary/5 border border-border/30">
              <CopilotNote markdown={callSummary} dense={paneled} />
            </div>
          </div>
        ) : tabbed ? (
          <p className="text-sm text-muted-foreground px-1">No note from this call.</p>
        ) : null}
        {tabbed ? noteExtra : null}
      </div>

      {/* 4. CRM FIELDS SECTION */}
      <div
        id={tabbed ? "review-panel-fields" : undefined}
        role={tabbed ? "tabpanel" : undefined}
        aria-labelledby={tabbed ? "review-tab-fields" : undefined}
        hidden={tabbed && activeTab !== "fields"}
        className={tabbed ? "space-y-4" : "space-y-4 pt-2"}
      >
        {renderFieldRail("fields", tabbed ? null : "Fields")}

        {/* Fields List */}
        {fieldEntries.length === 0 ? (
          <div className="p-6 text-center rounded-2xl bg-secondary/5 border border-dashed border-border/40">
            <p className="text-xs text-muted-foreground">
              {tabbed ? "Nothing to update on this record." : "No field updates extracted for this record."}
            </p>
          </div>
        ) : (
          <div className="grid gap-2">{renderUpdateRows(fieldEntries)}</div>
        )}
      </div>

      {tabbed ? (
        <div
          id="review-panel-tasks"
          role="tabpanel"
          aria-labelledby="review-tab-tasks"
          hidden={activeTab !== "tasks"}
          className="space-y-4"
        >
          {tasksLead}
          {renderFieldRail("tasks", null)}
          {taskEntries.length === 0 ? (
            <div className="p-6 text-center rounded-2xl bg-secondary/5 border border-dashed border-border/40">
              <p className="text-xs text-muted-foreground">No tasks from this call.</p>
            </div>
          ) : (
            <div className="grid gap-2">{renderUpdateRows(taskEntries, false)}</div>
          )}
        </div>
      ) : null}

      {tabbed ? tabPanels : null}

      {beforeConfirm}

      {paneled ? null : syncFooter}
    </div>
    </div>
      {paneled ? <div className="shrink-0 bg-card px-6 pb-4">{syncFooter}</div> : null}
    </div>
  );
};
