import { useState, useEffect, useCallback, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { crmApi } from "@/lib/api/crm";
import { memosApi } from "@/features/memos/api";
import { toast } from "sonner";
import {
  Check,
  AlertCircle,
  Sparkles,
  ChevronDown,
  Search,
  X,
  RefreshCw,
  Pencil,
  Trash2,
  Plus,
  UserCheck,
  Building,
  User,
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
import { CopilotNote } from "@/components/dashboard/CopilotNote";
import {
  clearCachedPreview,
  getCachedPreview,
  previewCacheKey,
  setCachedPreview,
} from "@/lib/preview-cache";

interface HubSpotSyncPreviewProps {
  memoId: string;
  initialDealId?: string | null;
  /** Bust preview cache when memo transcript/extraction changes */
  previewRefreshKey?: string;
  /** Structured call note from extraction — shown as the copilot summary */
  callSummary?: string | null;
  onSuccess: (data: any) => void;
  onContactName?: (name: string | null) => void;
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
  previewRefreshKey = "default",
  callSummary = "",
  onContactName,
}: HubSpotSyncPreviewProps) => {
  const [loading, setLoading] = useState(true);
  const [isSwitchingTarget, setIsSwitchingTarget] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [preview, setPreview] = useState<any>(null);
  const [extractionError, setExtractionError] = useState(false);
  const [retryKey, setRetryKey] = useState(0);
  const [reExtracting, setReExtracting] = useState(false);

  // Active target selection tracking
  const [selectedContactId, setSelectedContactId] = useState<string | null>(null);
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

  // Field edits
  const [editedUpdates, setEditedUpdates] = useState<any[] | null>(null);
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [showAddField, setShowAddField] = useState(false);
  const [omittedKeys, setOmittedKeys] = useState<string[]>([]);

  // Weak matches and manual deal naming
  const [needsDealDecision, setNeedsDealDecision] = useState(false);
  const [dealDecisionMade, setDealDecisionMade] = useState(true);
  const [weakMatches, setWeakMatches] = useState<any[]>([]);
  const [confirmingNewDeal, setConfirmingNewDeal] = useState(false);
  const [manualDealName, setManualDealName] = useState("");

  const searchQueryRef = useRef("");
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
      previewRefreshKey,
      selectedContactId,
      selectedDealId,
      isNewDealRequested,
      isSkipDealRequested,
      preview,
      applyPreviewDecisions,
    ],
  );

  useEffect(() => {
    let cancelled = false;
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
      setEditingIdx(null);
      setShowAddField(false);

      const cacheKey = previewCacheKey({
        memoId,
        dealId: initialDealId || null,
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
          await fetchPreview(initialDealId);
          return;
        }
        const previewData = await fetchPreview(undefined);
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
  }, [memoId, retryKey, initialDealId, previewRefreshKey, fetchPreview, applyPreviewDecisions]);

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

  const selectContact = async (contactId: string) => {
    setSelectedContactId(contactId);
    setContactPickerOpen(false);
    const data = await fetchPreview(selectedDealId, { contactId });
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

  const contactCandidates = Array.isArray(preview?.contact_candidates) ? preview.contact_candidates : [];
  const needsContactDecision = !selectedContact && contactCandidates.length > 0;
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
    setSyncing(true);
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
        },
      );
      toast.success(effectiveSkipDeal ? "Contact updated successfully!" : "CRM updated successfully!");
      onSuccess(result);
    } catch (err: any) {
      toast.error(err?.data?.detail || err?.message || "Failed to sync with CRM");
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
    setShowAddField(false);
    setEditingIdx(list.length);
  };

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
          <Button
            onClick={handleReExtract}
            disabled={reExtracting}
            variant="outline"
            className="mt-6 rounded-full border-beige/40 hover:bg-beige/10"
          >
            {reExtracting ? <VocifySpinner size={16} className="mr-2" /> : <RefreshCw className="h-4 w-4 mr-2" />}
            {reExtracting ? "Re-extracting..." : "Re-extract"}
          </Button>
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

  return (
    <div className="space-y-8 animate-in fade-in duration-300">
      {/* 1. CONTACT TARGET SECTION */}
      <div className="space-y-3">
        <div className="flex items-center justify-between px-1">
          <div className="flex items-center gap-2">
            <User className="h-4 w-4 text-beige" />
            <h5 className={THEME_TOKENS.typography.capsLabel}>Contact</h5>
          </div>
          {selectedContact && contactCandidates.length > 1 && !contactPickerOpen && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setContactPickerOpen(true)}
              className="text-xs font-normal text-beige hover:bg-beige/10 h-7 px-2.5 rounded-full"
            >
              Change Contact
            </Button>
          )}
        </div>

        {/* Contact Candidates Picker */}
        {(needsContactDecision || contactPickerOpen) && (
          <div className="bg-secondary/5 rounded-2xl p-5 border border-beige/25 space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium text-foreground">
                {contactCandidates.length > 1
                  ? "Several contacts matched — select who to update:"
                  : "Matched contact candidate:"}
              </p>
              {selectedContact && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 rounded-full"
                  onClick={() => setContactPickerOpen(false)}
                >
                  <X className="h-3.5 w-3.5" />
                </Button>
              )}
            </div>

            <div className="grid gap-2 max-h-60 overflow-y-auto pr-1 scrollbar-thin">
              {contactCandidates.map((c: any) => {
                const isSelected = selectedContact?.contact_id === c.contact_id;
                return (
                  <button
                    key={c.contact_id}
                    type="button"
                    onClick={() => selectContact(c.contact_id)}
                    className={`w-full text-left p-4 rounded-xl border transition-all ${
                      isSelected
                        ? "bg-beige/15 border-beige text-foreground shadow-sm"
                        : "bg-card hover:bg-beige/10 border-border/50 hover:border-beige/40"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-foreground truncate">{c.name || "Contact"}</p>
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
            </div>
          </div>
        )}

        {/* Selected Contact Card */}
        {selectedContact && !contactPickerOpen && (
          <div className="bg-secondary/5 rounded-2xl p-5 border border-border/40 hover:border-beige/30 transition-colors">
            <div className="flex items-start justify-between gap-4">
              <div className="space-y-1 min-w-0">
                <div className="flex items-center gap-2">
                  <UserCheck className="h-4 w-4 text-success shrink-0" />
                  <p className="text-sm font-medium text-foreground truncate">{selectedContact.name || "Contact"}</p>
                </div>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground pt-0.5">
                  {selectedContact.email && <span>{selectedContact.email}</span>}
                  {selectedContact.phone && <span>{selectedContact.phone}</span>}
                  {selectedContact.company_name && (
                    <span className="inline-flex items-center gap-1 font-medium text-foreground/80">
                      <Building className="h-3 w-3" />
                      {selectedContact.company_name}
                    </span>
                  )}
                </div>
                {selectedContact.match_reason && (
                  <p className="text-[10px] text-muted-foreground/50 pt-1">
                    {selectedContact.match_reason} — contact and company updates will link here
                  </p>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 2. DEAL TARGET SECTION */}
      <div className="space-y-3">
        <div className="flex items-center justify-between px-1">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-beige" />
            <h5 className={THEME_TOKENS.typography.capsLabel}>
              {selectedContact ? "Deal Target (optional)" : "Deal Target"}
            </h5>
          </div>
          {!dealPickerOpen && !(needsDealDecision && !dealDecisionMade) && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setDealPickerOpen(true)}
              className="text-xs font-normal text-beige hover:bg-beige/10 h-7 px-2.5 rounded-full"
            >
              <Search className="h-3 w-3 mr-1.5" />
              {dealMatch ? "Change Deal" : "Choose Deal"}
            </Button>
          )}
        </div>

        {/* Deal Picker Drawer (Search + Matched Deals + Create New + Contact Only) */}
        {(dealPickerOpen || (needsDealDecision && !dealDecisionMade)) && (
          <div className="bg-secondary/5 rounded-2xl p-5 border border-beige/30 space-y-4">
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
                  className="bg-card border-border/50 rounded-xl pl-10 pr-4 h-9 text-sm"
                />
              </div>
              <Button
                size="sm"
                onClick={handleSearch}
                disabled={isSearching}
                className="bg-beige text-cream hover:bg-beige-dark rounded-xl px-4 h-9 text-xs font-normal shrink-0"
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
                      <p className="text-sm font-medium text-foreground truncate">{d.deal_name}</p>
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
                        <p className="text-sm font-medium text-foreground truncate">{m.deal_name}</p>
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
                    className="bg-card border-border/50 rounded-xl px-3 h-9 text-sm flex-1"
                  />
                  <Button
                    size="sm"
                    onClick={confirmManualDealName}
                    disabled={!manualDealName.trim()}
                    className="bg-beige text-cream hover:bg-beige-dark rounded-xl px-4 h-9 text-xs font-normal shrink-0"
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

        {/* Selected Deal Card */}
        {!dealPickerOpen && !(needsDealDecision && !dealDecisionMade) && (
          <div
            className={`rounded-2xl p-5 border transition-all ${
              dealMatch
                ? "bg-success/[0.03] border-success/30"
                : skipDeal
                  ? "bg-secondary/5 border-border/40"
                  : isNewDeal
                    ? "bg-beige/[0.04] border-beige/30"
                    : "bg-secondary/5 border-border/40"
            }`}
          >
            <div className="flex items-start gap-3.5">
              <div
                className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${
                  dealMatch
                    ? "bg-success/15 text-success"
                    : skipDeal
                      ? "bg-secondary/20 text-muted-foreground"
                      : "bg-beige/20 text-beige"
                }`}
              >
                {dealMatch ? (
                  <Check className="h-4 w-4" />
                ) : skipDeal ? (
                  <UserCheck className="h-4 w-4" />
                ) : (
                  <Sparkles className="h-4 w-4" />
                )}
              </div>
              <div className="flex-1 space-y-0.5 min-w-0">
                <h4 className="text-sm font-medium text-foreground truncate">
                  {dealMatch
                    ? dealMatch.deal_name || "Existing Deal"
                    : skipDeal
                      ? "Contact Only"
                      : "New Deal Creation"}
                </h4>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  {dealMatch ? (
                    <span>
                      Targeting deal in CRM
                      {dealMatch.match_reason ? ` (${dealMatch.match_reason.toLowerCase()})` : ""}
                    </span>
                  ) : skipDeal ? (
                    <span>
                      Updating {selectedContact?.name || "contact"} record only — no deal will be created or updated.
                    </span>
                  ) : (
                    <span>A new deal will be created in your primary CRM pipeline.</span>
                  )}
                </p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 3. CALL NOTE / COPILOT SUMMARY */}
      {callSummary ? (
        <div className="space-y-3 pt-2">
          <h5 className={THEME_TOKENS.typography.sectionRail}>Call note</h5>
          <div className="p-5 rounded-2xl bg-secondary/5 border border-border/30">
            <CopilotNote markdown={callSummary} />
          </div>
        </div>
      ) : null}

      {/* 4. CRM FIELDS SECTION */}
      <div className="space-y-4 pt-2">
        <div className="relative flex items-center justify-between px-1">
          <div className="flex items-center gap-2">
            <h5 className={THEME_TOKENS.typography.sectionRail}>Fields</h5>
            {isSwitchingTarget && <VocifySpinner size={13} className="text-beige" />}
          </div>
          {availableFields.length > 0 && !loading && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowAddField(!showAddField)}
              className="h-auto px-2 py-1 text-xs font-normal text-beige hover:bg-beige/10 rounded-full"
            >
              <Plus className="h-3 w-3 mr-1" />
              Add field
            </Button>
          )}

          {/* Add Field Dropdown */}
          {showAddField && availableFields.length > 0 && (
            <div className="absolute right-1 top-full mt-2 z-20 w-64 max-h-56 overflow-y-auto py-2 rounded-2xl bg-popover border border-border/60 shadow-xl">
              {(() => {
                const unused = availableFields.filter((f: { name: string; object_type?: string }) => {
                  const ot = f.object_type || "deals";
                  return !updates.some((u: any) => u?.field_name === f.name && (u?.object_type || "deals") === ot);
                });
                const OBJECT_LABELS: Record<string, string> = {
                  deals: "Deal",
                  contacts: "Contact",
                  companies: "Company",
                };
                if (unused.length === 0) {
                  return <p className="px-4 py-2 text-xs text-muted-foreground">All available fields added</p>;
                }
                return unused.map(
                  (f: { name: string; label: string; type?: string; options?: unknown[]; object_type?: string }) => (
                    <button
                      key={`${f.object_type || "deals"}:${f.name}`}
                      onClick={() => addField(f)}
                      className="w-full text-left px-4 py-2 text-xs hover:bg-beige/10 transition-colors flex items-center justify-between"
                    >
                      <span className="font-medium text-foreground truncate">{f.label || f.name}</span>
                      <span className="text-[10px] text-muted-foreground/60 ml-2 shrink-0">
                        {OBJECT_LABELS[f.object_type || "deals"] || f.object_type}
                      </span>
                    </button>
                  ),
                );
              })()}
            </div>
          )}
        </div>

        {/* Fields List */}
        {updates.length === 0 ? (
          <div className="p-6 text-center rounded-2xl bg-secondary/5 border border-dashed border-border/40">
            <p className="text-xs text-muted-foreground">No field updates extracted for this record.</p>
          </div>
        ) : (
          <div className="grid gap-3">
            {sortedUpdateEntries.map(({ u: update, idx }) => {
              const hadExisting =
                update.current_value != null &&
                String(update.current_value).trim() !== "" &&
                String(update.current_value).trim() !== "(empty)";
              const isOverride = !!hadExisting;
              const canEditRow = canEditOrRemoveProposedField(update);
              const isEditing = editingIdx === idx;
              const entryPos = sortedUpdateEntries.findIndex((e) => e.idx === idx);
              const prevObject = entryPos > 0 ? sortedUpdateEntries[entryPos - 1].u?.object_type || "deals" : null;
              const currentObject = update.object_type || "deals";
              const showSection = entryPos === 0 || prevObject !== currentObject;
              const sectionLabel =
                {
                  deals: "Deal Properties",
                  contacts: "Contact Properties",
                  companies: "Company Properties",
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
                    className={`group relative rounded-2xl p-4 transition-all flex items-start justify-between gap-4 border ${
                      isOverride
                        ? "bg-destructive/[0.03] border-destructive/25 hover:border-destructive/40"
                        : "bg-card border-border/50 hover:border-beige/40 shadow-xs"
                    }`}
                  >
                    <div className="flex-1 min-w-0 space-y-1">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-medium text-muted-foreground">{update.field_label}</span>
                        {isOverride ? (
                          <span className="bg-destructive/10 text-destructive text-[10px] font-medium px-2 py-0.5 rounded-full shrink-0">
                            Override
                          </span>
                        ) : (
                          <span className="bg-success/10 text-success text-[10px] font-medium px-2 py-0.5 rounded-full shrink-0">
                            New
                          </span>
                        )}
                      </div>

                      {hadExisting && (
                        <p className="text-[10px] text-muted-foreground line-through opacity-60">
                          Was: {optionLabelFor(update.current_value, update.options) || "—"}
                        </p>
                      )}

                      {isEditing ? (
                        <div className="pt-1">
                          {update.options && update.options.length > 0 && !isCrmDateField(update) ? (
                            <select
                              autoFocus
                              value={String(update.new_value ?? "")}
                              onChange={(e) => updateField(idx, e.target.value)}
                              className="w-full h-9 rounded-xl border border-border bg-background px-3 text-xs font-medium focus:outline-none focus:ring-1 focus:ring-beige"
                            >
                              <option value="">—</option>
                              {update.options.map((o: { value: string; label?: string }) => (
                                <option key={o.value} value={o.value}>
                                  {o.label ?? o.value}
                                </option>
                              ))}
                            </select>
                          ) : isCrmDateField(update) ? (
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
                              className="h-9 rounded-xl text-xs"
                            />
                          )}
                        </div>
                      ) : (
                        <p
                          className={`text-sm font-normal leading-relaxed ${
                            isOverride ? "text-destructive" : "text-foreground"
                          }`}
                        >
                          {isCrmDateField(update)
                            ? formatCrmDateForDisplay(String(update.new_value ?? "")) || update.new_value || "—"
                            : optionLabelFor(update.new_value, update.options)}
                        </p>
                      )}
                    </div>

                    {canEditRow && !isEditing && (
                      <div className="flex items-center gap-1 shrink-0 pt-0.5 opacity-60 group-hover:opacity-100 transition-opacity">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 rounded-full text-muted-foreground hover:text-beige"
                          onClick={() => setEditingIdx(idx)}
                        >
                          <Pencil className="h-3 w-3" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 rounded-full text-muted-foreground hover:text-destructive"
                          onClick={() => removeField(idx)}
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 5. SYNC ACTION BUTTON */}
      <div className="pt-4 border-t border-border/40">
        <Button
          variant="hero"
          onClick={handleSync}
          disabled={syncing || loading || needsContactDecision || (needsDealDecision && !dealDecisionMade)}
          className="w-full bg-beige text-cream hover:bg-beige-dark rounded-full text-sm font-medium h-12 shadow-md transition-all"
        >
          {syncing ? <VocifySpinner size={16} className="mr-2" /> : <Check className="h-4 w-4 mr-2" />}
          {syncing
            ? "Syncing to CRM..."
            : needsContactDecision
              ? "Select a contact first"
              : needsDealDecision && !dealDecisionMade
                ? "Select a deal first"
                : skipDeal && selectedContact
                  ? "Confirm & Update Contact"
                  : dealMatch
                    ? "Confirm & Update Deal"
                    : "Confirm & Create Deal"}
        </Button>
      </div>
    </div>
  );
};
