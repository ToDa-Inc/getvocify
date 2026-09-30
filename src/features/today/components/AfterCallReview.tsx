import { useEffect, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { CopilotNote } from "@/components/dashboard/CopilotNote";
import { DoneMark } from "@/components/dashboard/DoneMark";
import { FollowupCard } from "@/components/dashboard/FollowupCard";
import { HubSpotSyncPreview } from "@/components/dashboard/hubspot/HubSpotSyncPreview";
import { memoKeys, memosApi } from "@/features/memos/api";
import {
  OTHER_REASON,
  REP_OUTCOMES,
  confirmTarget,
  dateInputValue,
  dealNote,
  dealRuleKey,
  draftProblems,
  followupStep,
  handoffHintKey,
  hintFailure,
  initialDraft,
  leadStatusChoice,
  needsReason,
  outcomeLabelKey,
  outcomePayload,
  type AfterCallContext,
  type AfterCallHint,
  type OutcomeDraft,
} from "@/lib/after-call-flow";
import { useLanguage } from "@/lib/i18n";
import { productText, type ProductTranslations } from "@/lib/product-catalog";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { ApiError } from "@/shared/lib/api-client";
import { todayKeys } from "../api";

const field = "h-8 w-full rounded-md border border-border bg-background px-2 text-[13px] text-foreground";
const quiet = "px-1 py-1.5 text-[13px] text-muted-foreground hover:text-foreground";
const hairline = "my-5 border-0 border-t border-[hsl(var(--hairline))]";

function errorText(error: unknown, fallback: string): string {
  const detail = error instanceof ApiError ? (error.data as { detail?: unknown } | null | undefined)?.detail : null;
  return typeof detail === "string" && detail.trim() ? detail : fallback;
}

function OutcomeStep({
  context,
  draft,
  onChange,
  copy,
}: {
  context: AfterCallContext;
  draft: OutcomeDraft;
  onChange: (next: OutcomeDraft) => void;
  copy: ProductTranslations;
}) {
  const lead = leadStatusChoice(context, draft);
  const note = dealNote(context, draft.outcome);
  return (
    <section aria-label={copy.after_call_outcome_title} className="space-y-3">
      <p className={THEME_TOKENS.typography.capsLabel}>{copy.after_call_outcome_title}</p>
      <div role="radiogroup" aria-label={copy.after_call_outcome_title} className="grid grid-cols-2 gap-1.5">
        {REP_OUTCOMES.map((outcome) => {
          const selected = draft.outcome === outcome;
          return (
            <button
              key={outcome}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => onChange({ ...draft, outcome, leadStatus: null })}
              className={`h-9 rounded-full border px-3 text-[13px] transition-colors ${
                selected
                  ? "border-beige bg-beige text-cream"
                  : "border-border/60 text-muted-foreground hover:border-border hover:text-foreground"
              }`}
            >
              {productText(outcomeLabelKey(outcome), copy)}
            </button>
          );
        })}
      </div>

      {draft.outcome === "follow_up" ? (
        <label className="flex items-center justify-between gap-3 text-[13px] text-muted-foreground">
          <span>{copy.after_call_followup_date}</span>
          <input
            type="date"
            className={`${field} w-auto`}
            value={draft.followupDate}
            onChange={(event) => onChange({ ...draft, followupDate: event.target.value })}
          />
        </label>
      ) : null}

      {needsReason(draft.outcome) ? (
        <div className="space-y-1.5">
          <select
            aria-label={copy.after_call_reason}
            className={field}
            value={draft.reason}
            onChange={(event) => onChange({ ...draft, reason: event.target.value })}
          >
            <option value="">{copy.after_call_reason_pick}</option>
            {context.lost_reasons.map((reason) => (
              <option key={reason} value={reason}>{reason}</option>
            ))}
            <option value={OTHER_REASON}>{copy.after_call_reason_other}</option>
          </select>
          {draft.reason === OTHER_REASON ? (
            <input
              type="text"
              aria-label={copy.after_call_reason}
              placeholder={copy.after_call_reason_other_placeholder}
              className={field}
              value={draft.otherReason}
              onChange={(event) => onChange({ ...draft, otherReason: event.target.value })}
            />
          ) : null}
        </div>
      ) : null}

      {lead ? (
        lead.value || lead.editable ? (
          <label className="flex items-center justify-between gap-3 text-[13px] text-muted-foreground">
            <span>{copy.after_call_lead_status}</span>
            {lead.editable ? (
              <select
                className={`${field} w-auto`}
                value={lead.value ?? ""}
                onChange={(event) => onChange({ ...draft, leadStatus: event.target.value || null })}
              >
                {lead.proposed ? null : <option value="">—</option>}
                {lead.options.map((value) => (
                  <option key={value} value={value}>{value}</option>
                ))}
              </select>
            ) : (
              <span className="text-foreground">{lead.value}</span>
            )}
          </label>
        ) : (
          <p className="text-[12px] text-muted-foreground">{copy.after_call_lead_status_unmapped}</p>
        )
      ) : null}

      {note ? (
        <p className="text-[12px] text-muted-foreground">
          {note.kind === "creates" ? copy.after_call_deal_creates : productText(dealRuleKey(note.rule), copy)}
        </p>
      ) : null}
    </section>
  );
}

/**
 * Lista 4 T4 (E10, AFTER_CALL_FLOW_ENABLED): after hanging up, without leaving Hoy - the CRM
 * proposal (fields + note, the same review MemoDetail uses), the required outcome, Confirmar,
 * then the follow-up. The "next call" link stays ContactPanel's. A memo auto-approve already
 * wrote only needs the outcome (POST /outcome); the backend enforces every rule shown here.
 */
export function AfterCallReview({
  memoId,
  crmName,
  onOpenMemo,
  registerSend,
  handoffFallback,
}: {
  memoId: string;
  crmName: string | null;
  onOpenMemo: (memoId: string) => void;
  registerSend?: (send: (() => void) | null) => void;
  /** Rendered when the booked meeting still needs an AE picked (the panel's handoff form). */
  handoffFallback?: ReactNode;
}) {
  const { t } = useLanguage();
  const copy = t.product;
  const queryClient = useQueryClient();
  const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;

  const contextQuery = useQuery({
    queryKey: ["after-call", memoId],
    queryFn: () => memosApi.afterCall(memoId),
    staleTime: 30_000,
    retry: false,
  });
  const memoQuery = useQuery({
    queryKey: memoKeys.detail(memoId),
    queryFn: () => memosApi.get(memoId),
    staleTime: 30_000,
  });
  const context = contextQuery.data ?? null;
  const memo = memoQuery.data;

  const [draft, setDraft] = useState<OutcomeDraft>(() => initialDraft(null));
  const [saved, setSaved] = useState<AfterCallHint | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [followupRevealed, setFollowupRevealed] = useState(false);

  const suggested = context?.suggested_followup_at;
  useEffect(() => {
    if (!suggested) return;
    setDraft((prev) => (prev.followupDate ? prev : { ...prev, followupDate: dateInputValue(suggested, timeZone) }));
  }, [suggested, timeZone]);

  if (contextQuery.isPending) {
    return <p className={THEME_TOKENS.typography.body}>{copy.after_call_loading}</p>;
  }
  if (!context) {
    return (
      <div className="flex flex-wrap items-center gap-2" role="alert">
        <p className={THEME_TOKENS.typography.body}>{copy.after_call_load_failed}</p>
        <button type="button" className={quiet} onClick={() => void contextQuery.refetch()}>
          {copy.after_call_retry}
        </button>
      </div>
    );
  }

  const payload = outcomePayload(draft, context, { offsetMinutes: -new Date().getTimezoneOffset(), timeZone });
  const problem = draftProblems(draft)[0];
  const blocked =
    problem === "outcome"
      ? copy.after_call_pick_outcome
      : problem === "reason"
        ? copy.after_call_pick_reason
        : problem === "date"
          ? copy.after_call_pick_date
          : null;

  const finish = (hint: AfterCallHint | null | undefined) => {
    const failure = hintFailure(hint);
    if (failure) {
      setError(failure);
      return;
    }
    setError(null);
    setSaved(hint ?? {});
    void queryClient.invalidateQueries({ queryKey: todayKeys.view() });
    void queryClient.invalidateQueries({ queryKey: memoKeys.detail(memoId) });
  };

  const confirmOutcome = async () => {
    if (!payload) return;
    setSaving(true);
    setError(null);
    try {
      const result = await memosApi.recordOutcome(memoId, payload);
      finish(result.after_call);
    } catch (failure) {
      setError(errorText(failure, copy.after_call_failed));
    } finally {
      setSaving(false);
    }
  };

  // Recorded earlier (the rep came back to this contact): show it as done, not as a new form.
  const done: AfterCallHint | null =
    saved ?? (context.rep_outcome && context.memo_status === "approved"
      ? { rep_outcome: context.rep_outcome, followup_at: context.followup_at }
      : null);

  if (done) {
    const outcome = done.rep_outcome ?? draft.outcome;
    const dateLine = done.followup_at
      ? copy.after_call_saved_followup.replace(
          "{date}",
          new Intl.DateTimeFormat(copy.hourLocale, { weekday: "short", day: "numeric", month: "short" }).format(new Date(done.followup_at)),
        )
      : null;
    const savedLine = done.crm?.status === "unsupported" || !crmName
      ? copy.after_call_saved
      : copy.after_call_saved_crm.replace("{crm}", crmName);
    const handoffKey = handoffHintKey(done);
    const step = followupStep(context, followupRevealed);
    return (
      <div className="space-y-2">
        <p className="flex items-center gap-2 text-[14px] text-foreground">
          {/* Plays on the save the rep just confirmed; rests on one recorded earlier. */}
          <DoneMark size={20} animate={Boolean(saved)} />
          <span>{[savedLine, outcome ? productText(outcomeLabelKey(outcome), copy) : null, dateLine].filter(Boolean).join(" · ")}</span>
        </p>
        {done.crm?.status === "unsupported" && crmName ? (
          <p className="text-[12px] text-muted-foreground">{copy.after_call_crm_unsupported.replace("{crm}", crmName)}</p>
        ) : null}
        {done.crm?.warning ? <p className="text-[12px] text-muted-foreground">{done.crm.warning}</p> : null}
        {done.deal?.status === "not_created_after_approval" ? (
          <p className="text-[12px] text-muted-foreground">{copy.after_call_deal_not_created}</p>
        ) : null}
        {handoffKey ? <p className="text-[13px] text-muted-foreground">{productText(handoffKey, copy)}</p> : null}
        {handoffKey === "after_call_handoff_needs_ae" ? handoffFallback : null}

        <hr className={hairline} />
        {step === "card" ? (
          <section aria-label={copy.panel_followup}>
            <p className={`mb-2 ${THEME_TOKENS.typography.capsLabel}`}>{copy.panel_followup}</p>
            <FollowupCard memoId={memoId} onSendReady={registerSend} />
          </section>
        ) : (
          <button type="button" className={quiet} onClick={() => setFollowupRevealed(true)}>
            {copy.after_call_followup_link}
          </button>
        )}
      </div>
    );
  }

  const outcomeStep = <OutcomeStep context={context} draft={draft} onChange={setDraft} copy={copy} />;

  if (confirmTarget(context.memo_status) === "approve") {
    return (
      <section aria-label={copy.after_call_proposal}>
        <p className={`mb-3 ${THEME_TOKENS.typography.capsLabel}`}>{copy.after_call_proposal}</p>
        <HubSpotSyncPreview
          compact
          memoId={memoId}
          initialContactId={memo?.hubspotContactId ?? null}
          fallbackContactName={memo?.extraction?.contactName ?? null}
          previewRefreshKey={memo ? `${memo.id}:${memo.processedAt ?? ""}` : "default"}
          callSummary={memo?.extraction?.summary ?? null}
          beforeConfirm={outcomeStep}
          approveExtra={payload}
          confirmBlockedLabel={blocked}
          confirmLabel={copy.after_call_confirm}
          onSuccess={(result: { after_call?: AfterCallHint | null } | null) => finish(result?.after_call ?? null)}
        />
        {error ? <p role="alert" className="mt-2 text-[12px] text-destructive">{error}</p> : null}
      </section>
    );
  }

  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <p className="text-[13px] text-muted-foreground">{copy.after_call_already_saved}</p>
        {memo?.extraction?.summary ? (
          <section aria-label={copy.after_call_note} className="rounded-2xl border border-border/30 bg-secondary/5 p-4">
            <CopilotNote markdown={memo.extraction.summary} />
          </section>
        ) : null}
        <button type="button" className={quiet} onClick={() => onOpenMemo(memoId)}>
          {copy.after_call_open_fields}
        </button>
      </div>
      {outcomeStep}
      <div>
        <Button
          type="button"
          className="h-11 w-full rounded-full bg-beige px-[18px] text-[15px] font-normal text-cream hover:bg-beige-dark"
          disabled={saving || Boolean(blocked)}
          onClick={() => void confirmOutcome()}
        >
          {saving ? copy.after_call_saving : blocked ?? copy.after_call_confirm}
        </Button>
        {error ? (
          <div role="alert" className="mt-2 flex flex-wrap items-center gap-2 text-[12px] text-destructive">
            <span>{error}</span>
            <button type="button" className={quiet} disabled={saving} onClick={() => void confirmOutcome()}>
              {copy.after_call_retry}
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
