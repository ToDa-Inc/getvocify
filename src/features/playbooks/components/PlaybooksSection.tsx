import { useEffect, useState } from "react";
import { useAuth } from "@/features/auth";
import { PlaybookEditor } from "@/features/playbooks/components/PlaybookEditor";
import { PlaybookSetupNotice } from "@/features/playbooks/components/PlaybookSetupNotice";
import {
  applyFetchedMotions,
  applyPublishResult,
  flowLabel,
  motionAfterImport,
  playbookNotice,
  visiblePlaybookKeys,
  type MotionStatus,
  type PlaybookRole,
} from "@/lib/playbook-setup";
import { Button } from "@/components/ui/button";
import { useLanguage } from "@/lib/i18n";
import { motionLabel } from "@/lib/motion-label";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { api } from "@/shared/lib/api-client";

const MOTIONS = ["discovery", "qualification", "closing"] as const;
const field = "block w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground";

function roleOf(value: string | null | undefined): PlaybookRole {
  if (value === "owner" || value === "admin" || value === "member") return value;
  return "member";
}

export default function PlaybooksSection() {
  const { t } = useLanguage();
  const { user } = useAuth();
  const role = roleOf(user?.company?.role);
  const salesRolesEnabled = Boolean(user?.company?.features?.includes("SALES_ROLES_ENABLED"));
  const [motions, setMotions] = useState<Record<string, MotionStatus>>({
    discovery: "missing",
    qualification: "missing",
    closing: "missing",
  });
  const [goals, setGoals] = useState<Record<string, string>>({});
  const [typeKey, setTypeKey] = useState("");
  const [openKey, setOpenKey] = useState<string | null>(null);
  const notice = playbookNotice(role, motions);
  const keys = visiblePlaybookKeys(MOTIONS, motions, salesRolesEnabled);
  const activeKey = salesRolesEnabled ? openKey ?? keys[0] ?? null : openKey;

  useEffect(() => {
    let cancelled = false;
    api
      .get<{ motions: Record<string, MotionStatus>; goals?: Record<string, string> }>("/playbooks")
      .then((data) => {
        if (cancelled) return;
        setMotions((current) => applyFetchedMotions(current, data.motions, salesRolesEnabled));
        if (data.goals) setGoals(data.goals);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [salesRolesEnabled]);

  /** PDF/audio -> text only. No sales_motion_key, so the server never stores the raw text
   * as a one-block draft: the editor turns it into steps and saves those. */
  async function importText(kind: "pdf" | "audio", payload: string) {
    const record = await api.post<{ status: string; published: boolean; reason?: string | null; draft?: { text?: string } | null }>(
      "/playbooks/imports",
      { import_id: crypto.randomUUID(), kind, payload },
    );
    const outcome = motionAfterImport("missing", record);
    return { text: record.draft?.text ?? null, error: outcome.error };
  }

  async function publish(key: string): Promise<boolean> {
    try {
      const data = await api.post<{ motions: Record<string, MotionStatus> }>(
        `/playbooks/${key}/publish`,
      );
      setMotions((current) =>
        applyPublishResult(current, key, {
          ok: data.motions[key] === "published",
          salesMotionKey: key,
          status: data.motions[key],
        }),
      );
      return data.motions[key] === "published";
    } catch {
      return false;
    }
  }

  async function addType() {
    const key = typeKey.trim();
    if (!key) return;
    const data = await api.post<{ motions: Record<string, MotionStatus> }>("/playbooks/types", {
      type_key: key,
      name: key,
    });
    setMotions((current) => ({ ...current, ...data.motions }));
    setTypeKey("");
  }

  function flowKeyLabel(key: string): string {
    return flowLabel(key, motionLabel(key, t.product.motions), t.product.playbookFlowLabels, salesRolesEnabled);
  }

  function goalKeyLabel(key: string): string | null {
    const goal = goals[key];
    if (!goal) return null;
    return (t.product.playbookGoalLabels as Record<string, string>)[goal] ?? null;
  }

  function renderEditor(key: string) {
    return (
      <PlaybookEditor
        key={key}
        motionKey={key}
        canEdit={notice.canEdit}
        status={motions[key] || "missing"}
        importText={importText}
        publish={() => publish(key)}
        onStatus={(next) => setMotions((current) => ({ ...current, [key]: next }))}
      />
    );
  }

  const statusLabel: Record<MotionStatus, string> = {
    missing: t.product.playbookStatusMissing,
    draft: t.product.playbookStatusDraft,
    importing: t.product.playbookStatusImporting,
    published: t.product.playbookStatusPublished,
  };

  return (
    <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} space-y-5 p-6 md:p-8`}>
      <h2 className={THEME_TOKENS.typography.sectionTitle}>{t.product.playbookTitle}</h2>
      <PlaybookSetupNotice role={role} motions={motions} />
      {notice.canEdit ? (
        <details>
          <summary className={`${THEME_TOKENS.typography.capsLabel} cursor-pointer`}>{t.product.playbookAddType}</summary>
        <form
          className="mt-3 flex flex-wrap gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            void addType();
          }}
        >
          <input
            className={`${field} max-w-xs`}
            value={typeKey}
            placeholder={t.product.playbookNewTypePlaceholder}
            onChange={(event) => setTypeKey(event.target.value)}
          />
          <Button type="submit" variant="outline" size="sm">
            {t.product.playbookAddType}
          </Button>
        </form>
        </details>
      ) : null}
      {salesRolesEnabled ? (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2" role="tablist">
            {keys.map((key) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={activeKey === key}
                className={`rounded-lg px-3 py-2 text-sm ${
                  activeKey === key ? "bg-secondary text-foreground" : "bg-secondary/40 text-muted-foreground"
                }`}
                onClick={() => setOpenKey(key)}
              >
                {flowKeyLabel(key)}
              </button>
            ))}
          </div>
          {activeKey ? (
            <div className="rounded-lg bg-secondary/40 px-4 py-4">
              <div className="flex w-full items-center justify-between gap-3 text-left">
                <span className="text-[15px] text-foreground">{flowKeyLabel(activeKey)}</span>
                <span className={THEME_TOKENS.typography.capsLabel}>
                  {statusLabel[motions[activeKey] || "missing"]}
                </span>
              </div>
              {goalKeyLabel(activeKey) ? (
                <p className={`mt-1 ${THEME_TOKENS.typography.capsLabel}`}>{goalKeyLabel(activeKey)}</p>
              ) : null}
              {renderEditor(activeKey)}
            </div>
          ) : null}
        </div>
      ) : (
        <ul className="space-y-3">
          {keys.map((key) => (
            <li key={key} className="rounded-lg bg-secondary/40 px-4 py-4">
              <button
                type="button"
                className="flex w-full items-center justify-between gap-3 text-left"
                onClick={() => setOpenKey((current) => (current === key ? null : key))}
              >
                <span className="text-[15px] text-foreground">{motionLabel(key, t.product.motions)}</span>
                <span className={THEME_TOKENS.typography.capsLabel}>
                  {statusLabel[motions[key] || "missing"]}
                </span>
              </button>
              {openKey === key ? renderEditor(key) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
